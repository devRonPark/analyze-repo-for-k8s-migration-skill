"""Lock the Secret-safe per-question exploration coverage ledger (Task 2).

The ledger records that a question was *touched* by an observation -- never
the observed value, path text, or excerpt itself. It is measurement only:
recording coverage must never promote a value into a grounded finding.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from migration_assistant.adk_tools import AdkRepositoryToolset, DuplicateTracker, ValidationLedger
from migration_assistant.exploration_ledger import ExplorationLedger
from migration_assistant.repository_tools import RepositoryTools
from migration_assistant.target import SafetyBudget


class ExplorationLedgerTests(unittest.TestCase):
    def test_observed_question_is_not_reported_as_grounded_value(self):
        ledger = ExplorationLedger()
        ledger.record_observation("production_startup", "read_file_lines", "Dockerfile", 1, 3)
        summary = ledger.summary()
        self.assertEqual(summary["questions"]["production_startup"]["status"], "observed")
        self.assertNotIn("value", repr(summary))

    def test_unobserved_question_is_absent_from_summary(self):
        ledger = ExplorationLedger()
        ledger.record_observation("production_startup", "search_text", "Dockerfile", 1, 1)
        self.assertNotIn("receiving_port", ledger.summary()["questions"])

    def test_observation_count_and_bounded_line_count_accumulate(self):
        ledger = ExplorationLedger()
        ledger.record_observation("production_startup", "search_text", "Dockerfile", 1, 1)
        ledger.record_observation("production_startup", "read_file_lines", "Dockerfile", 1, 3)
        summary = ledger.summary()["questions"]["production_startup"]
        self.assertEqual(summary["observation_count"], 2)
        self.assertEqual(summary["observed_line_count"], 4)

    def test_observed_line_count_is_bounded_per_observation(self):
        ledger = ExplorationLedger()
        ledger.record_observation("production_startup", "read_file", "Dockerfile", 1, 500)
        summary = ledger.summary()["questions"]["production_startup"]
        self.assertLessEqual(summary["observed_line_count"], 10)

    def test_positive_evidence_count_only_increments_when_flagged(self):
        ledger = ExplorationLedger()
        ledger.record_observation("production_startup", "search_text", "Dockerfile", 1, 1)
        ledger.record_observation("production_startup", "read_file_lines", "Dockerfile", 1, 1, positive=True)
        summary = ledger.summary()["questions"]["production_startup"]
        self.assertEqual(summary["positive_evidence_count"], 1)

    def test_tool_names_are_deduplicated(self):
        ledger = ExplorationLedger()
        ledger.record_observation("production_startup", "search_text", "Dockerfile", 1, 1)
        ledger.record_observation("production_startup", "search_text", "Dockerfile", 2, 2)
        summary = ledger.summary()["questions"]["production_startup"]
        self.assertEqual(summary["tool_names"], ["search_text"])

    def test_ledger_never_retains_raw_path_or_excerpt(self):
        ledger = ExplorationLedger()
        ledger.record_observation("runtime_config_and_secret_names", "read_file_lines", "config/application.yml", 4, 4)
        rendered = repr(ledger.summary())
        self.assertNotIn("application.yml", rendered)

    def test_summary_covers_multiple_questions_independently(self):
        ledger = ExplorationLedger()
        ledger.record_observation("production_startup", "read_file_lines", "Dockerfile", 1, 1)
        ledger.record_observation("receiving_port", "search_text", "Dockerfile", 2, 2)
        summary = ledger.summary()["questions"]
        self.assertEqual(set(summary), {"production_startup", "receiving_port"})


class ExplorationLedgerAdkWiringTests(unittest.TestCase):
    """Task 2 Step 3: Tool result -> ExplorationLedger update, without a live model."""

    def make_repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
        (repo / "Dockerfile").write_text('FROM python:3.11\nENTRYPOINT ["python", "app.py"]\n', encoding="utf-8")
        return repo

    def test_toolset_owns_an_exploration_ledger_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            toolset = AdkRepositoryToolset(RepositoryTools(repo, budget=SafetyBudget()), ValidationLedger(), DuplicateTracker())
            self.assertIsInstance(toolset.exploration_ledger, ExplorationLedger)

    def test_search_text_hit_updates_exploration_coverage_for_matched_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            toolset = AdkRepositoryToolset(RepositoryTools(repo, budget=SafetyBudget()), ValidationLedger(), DuplicateTracker())

            toolset.search_text("ENTRYPOINT", ".")

            coverage = toolset.exploration_ledger.summary()["questions"]
            self.assertIn("production_startup", coverage)
            self.assertEqual(coverage["production_startup"]["tool_names"], ["search_text"])

    def test_unrelated_observation_records_no_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            (repo / "README.md").write_text("hello world\n", encoding="utf-8")
            toolset = AdkRepositoryToolset(RepositoryTools(repo, budget=SafetyBudget()), ValidationLedger(), DuplicateTracker())

            toolset.search_text("hello", ".")

            self.assertEqual(toolset.exploration_ledger.summary()["questions"], {})

    def test_exploration_coverage_never_leaks_the_observed_path_in_repr(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            toolset = AdkRepositoryToolset(RepositoryTools(repo, budget=SafetyBudget()), ValidationLedger(), DuplicateTracker())

            toolset.search_text("ENTRYPOINT", ".")

            self.assertNotIn("Dockerfile", repr(toolset.exploration_ledger.summary()))

    def test_accepted_positive_evidence_increments_positive_evidence_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            toolset = AdkRepositoryToolset(RepositoryTools(repo, budget=SafetyBudget()), ValidationLedger(), DuplicateTracker())
            toolset.inspect_target()

            response = toolset.validate_analysis(
                status="partial",
                summary="기동 명령을 확인했습니다.",
                evidence=[
                    {
                        "id": "e1",
                        "status": "confirmed",
                        "path": "Dockerfile",
                        "line_start": 2,
                        "line_end": 2,
                        "claim": "기동 명령",
                        "text": 'ENTRYPOINT ["python", "app.py"]',
                    }
                ],
                findings=[],
                iterations=1,
                errors=["writable path는 확인하지 못했습니다."],
            )

            self.assertTrue(response["ok"], response)
            coverage = toolset.exploration_ledger.summary()["questions"]
            self.assertIn("production_startup", coverage)
            self.assertEqual(coverage["production_startup"]["positive_evidence_count"], 1)

    def test_unresolved_evidence_never_counts_as_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            toolset = AdkRepositoryToolset(RepositoryTools(repo, budget=SafetyBudget()), ValidationLedger(), DuplicateTracker())
            toolset.inspect_target()

            toolset.validate_analysis(
                status="partial",
                summary="확인하지 못했습니다.",
                evidence=[
                    {
                        "id": "e1",
                        "status": "unresolved",
                        "absence_scope": "Dockerfile*",
                        "absence_pattern": "VOLUME",
                        "result": "no match",
                    }
                ],
                findings=[],
                iterations=1,
                errors=["writable path는 확인하지 못했습니다."],
            )

            self.assertEqual(toolset.exploration_ledger.summary()["questions"], {})

    def test_injected_exploration_ledger_is_used_instead_of_a_new_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            ledger = ExplorationLedger()
            toolset = AdkRepositoryToolset(
                RepositoryTools(repo, budget=SafetyBudget()),
                ValidationLedger(),
                DuplicateTracker(),
                exploration_ledger=ledger,
            )

            toolset.search_text("ENTRYPOINT", ".")

            self.assertIs(toolset.exploration_ledger, ledger)
            self.assertIn("production_startup", ledger.summary()["questions"])


if __name__ == "__main__":
    unittest.main()
