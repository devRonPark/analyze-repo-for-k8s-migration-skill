from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from migration_assistant.adk_tools import AdkRepositoryToolset, DuplicateTracker, ValidationLedger
from migration_assistant.provenance import ObservationProvenance, evidence_sources
from migration_assistant.repository_tools import RepositoryTools
from migration_assistant.target import SafetyBudget


class ObservationProvenanceTests(unittest.TestCase):
    def test_source_is_reported_only_when_every_line_was_observed(self):
        provenance = ObservationProvenance()
        provenance.record("search_text", "app.py", 10, 10)
        provenance.record("read_file_lines", "app.py", 10, 12)

        self.assertEqual(provenance.sources_for("app.py", 10, 10), ("read_file_lines", "search_text"))
        self.assertEqual(provenance.sources_for("app.py", 10, 12), ("read_file_lines",))
        self.assertEqual(provenance.sources_for("app.py", 9, 10), ())
        self.assertEqual(provenance.sources_for("other.py", 10, 10), ())

    def test_cap_stops_recording_and_reports_incompleteness(self):
        provenance = ObservationProvenance(max_lines=4)
        provenance.record("read_file", "big.txt", 1, 10)

        self.assertTrue(provenance.truncated)
        self.assertEqual(provenance.sources_for("big.txt", 1, 10), ())
        # A cap must never be silent; measurement has to know the record is partial.
        self.assertTrue(provenance.summary()["truncated"])

    def test_summary_counts_lines_per_tool_without_repository_content(self):
        provenance = ObservationProvenance()
        provenance.record("search_text", "app.py", 1, 1)
        provenance.record("read_file", "app.py", 1, 3)

        summary = provenance.summary()

        self.assertEqual(summary["observed_lines"]["search_text"], 1)
        self.assertEqual(summary["observed_lines"]["read_file"], 3)
        self.assertFalse(summary["truncated"])


class ToolsetProvenanceRecordingTests(unittest.TestCase):
    @staticmethod
    def init_repository(root: Path) -> None:
        subprocess.run(["git", "init", "--quiet", str(root)], check=False)

    def make_toolset(self, root: Path, budget: SafetyBudget | None = None) -> AdkRepositoryToolset:
        self.init_repository(root)
        repository = RepositoryTools(root, budget=budget or SafetyBudget())
        return AdkRepositoryToolset(repository, ValidationLedger(), DuplicateTracker())

    def test_search_text_and_read_file_lines_record_their_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("one\nPORT = 8080\nthree\n", encoding="utf-8")
            toolset = self.make_toolset(root)

            toolset.search_text("PORT", ".")
            toolset.read_file_lines("app.py", 3, 3)

            provenance = toolset.provenance
            self.assertEqual(provenance.sources_for("app.py", 2, 2), ("search_text",))
            self.assertEqual(provenance.sources_for("app.py", 3, 3), ("read_file_lines",))

    def test_read_file_records_returned_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
            toolset = self.make_toolset(root)

            toolset.read_file("app.py")

            self.assertEqual(toolset.provenance.sources_for("app.py", 1, 3), ("read_file",))

    def test_truncated_read_file_never_claims_the_partial_last_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            line = "x" * 100
            (root / "big.txt").write_text("\n".join([line] * 40) + "\n", encoding="utf-8")
            # 101 bytes per line, so a 250-byte prefix keeps two whole lines and
            # cuts the third in half.
            toolset = self.make_toolset(root, SafetyBudget(max_tool_response_bytes=250))

            returned = toolset.read_file("big.txt")["data"]

            self.assertTrue(returned["truncated"])
            observed = toolset.provenance.summary()["observed_lines"].get("read_file", 0)
            # The byte prefix cuts the third line in half; only whole lines may count.
            self.assertEqual(observed, 2)
            self.assertEqual(toolset.provenance.sources_for("big.txt", 3, 3), ())

    def test_provenance_output_excludes_repository_text_and_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            secret = "sk-live-0123456789abcdef"
            (root / "app.py").write_text(f'TOKEN = "{secret}"\n', encoding="utf-8")
            toolset = self.make_toolset(root)

            toolset.search_text("TOKEN", ".")
            payload = json.dumps(toolset.provenance.summary(), ensure_ascii=False)

            self.assertNotIn(secret, payload)
            self.assertNotIn("TOKEN", payload)


class SearchEffectivenessTests(unittest.TestCase):
    def test_summary_reports_zero_hit_ratio(self):
        provenance = ObservationProvenance()
        provenance.record_search(8)
        provenance.record_search(0)
        provenance.record_search(0)

        summary = provenance.summary()

        self.assertEqual(summary["search_calls"], 3)
        self.assertEqual(summary["search_zero_hit_calls"], 2)

    def test_no_search_call_reports_no_ratio_instead_of_zero(self):
        summary = ObservationProvenance().summary()

        self.assertEqual(summary["search_calls"], 0)
        self.assertEqual(summary["search_zero_hit_calls"], 0)
        # A run that never searched must not look like a run that searched perfectly.
        self.assertIsNone(summary["search_zero_hit_ratio"])

    def test_toolset_records_hit_counts_without_the_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            secret = "sk-live-0123456789abcdef"
            (root / "app.py").write_text(f'PORT = 8080\nTOKEN = "{secret}"\n', encoding="utf-8")
            toolset = ToolsetProvenanceRecordingTests().make_toolset(root)

            toolset.search_text("PORT", ".")
            toolset.search_text("NOTHING_MATCHES_THIS", ".")

            summary = toolset.provenance.summary()
            self.assertEqual(summary["search_calls"], 2)
            self.assertEqual(summary["search_zero_hit_calls"], 1)
            self.assertEqual(summary["search_zero_hit_ratio"], 0.5)
            payload = json.dumps(summary, ensure_ascii=False)
            self.assertNotIn("NOTHING_MATCHES_THIS", payload)
            self.assertNotIn(secret, payload)

    def test_failed_search_is_not_counted_as_a_zero_hit_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("PORT = 8080\n", encoding="utf-8")
            toolset = ToolsetProvenanceRecordingTests().make_toolset(root)

            # An invalid regex is a protocol error, not evidence that the
            # repository lacks the term.
            toolset.search_text("(unclosed", ".")

            self.assertEqual(toolset.provenance.summary()["search_calls"], 0)


class EvidenceSourceAttributionTests(unittest.TestCase):
    def test_positive_evidence_is_attributed_to_the_tools_that_observed_it(self):
        provenance = ObservationProvenance()
        provenance.record("read_file", "pom.xml", 1, 200)
        provenance.record("read_file_lines", "pom.xml", 62, 62)

        attribution = evidence_sources(
            [
                {"id": "e1", "status": "confirmed", "path": "pom.xml", "line_start": 62, "line_end": 62},
                {"id": "e2", "status": "confirmed", "path": "pom.xml", "line_start": 13, "line_end": 13},
                {"id": "e3", "status": "confirmed", "path": "app.py", "line_start": 1, "line_end": 1},
            ],
            provenance,
        )

        self.assertEqual(attribution[0], {"id": "e1", "sources": ["read_file", "read_file_lines"]})
        # Read as part of a whole-file read but never pinpointed.
        self.assertEqual(attribution[1], {"id": "e2", "sources": ["read_file"]})
        # Cited without ever being observed.
        self.assertEqual(attribution[2], {"id": "e3", "sources": []})

    def test_unresolved_absence_evidence_is_not_attributed(self):
        attribution = evidence_sources(
            [{"id": "a1", "status": "unresolved", "absence_scope": ".", "absence_pattern": "x", "result": "없음"}],
            ObservationProvenance(),
        )

        self.assertEqual(attribution, [])


if __name__ == "__main__":
    unittest.main()
