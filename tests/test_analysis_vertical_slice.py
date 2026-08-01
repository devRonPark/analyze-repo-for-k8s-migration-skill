from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from migration_assistant.analysis import AnalysisResult, EvidenceStatus, PYDANTIC_AVAILABLE, analyze
from migration_assistant.cli import main


class Planner:
    def __init__(self, actions):
        self.actions = iter(actions)

    def next_action(self, observation):
        return next(self.actions)


class AnalysisVerticalSliceTests(unittest.TestCase):
    def make_repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
        (repo / "app.py").write_text("PORT = 8080\nAPI_KEY = top-secret\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "app.py"], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "--quiet", "-m", "fixture"], check=True)
        return repo

    def test_analysis_result_rejects_extra_fields_and_invalid_lines(self):
        self.assertTrue(PYDANTIC_AVAILABLE)
        with self.assertRaises(ValueError):
            AnalysisResult.model_validate({"status": "complete", "evidence": [], "summary": "ok", "extra": True})
        with self.assertRaises(ValueError):
            AnalysisResult.model_validate({"status": "complete", "summary": "ok", "evidence": [{"status": "confirmed", "path": "app.py", "line_start": 0, "line_end": 1}]})

    def test_evidence_statuses_and_line_provenance_are_preserved(self):
        result = AnalysisResult.model_validate({
            "status": "partial",
            "summary": "분석이 부분 완료되었습니다.",
            "evidence": [
                {"status": EvidenceStatus.CONFIRMED.value, "path": "app.py", "line_start": 1, "line_end": 1, "text": "PORT = 8080"},
                {"status": EvidenceStatus.UNRESOLVED.value, "absence_scope": "**/*.java", "absence_pattern": "main"},
                {"status": EvidenceStatus.CONFLICTING.value, "path": "app.py", "line_start": 1, "line_end": 1},
                {"status": EvidenceStatus.INFERRED.value, "path": "app.py", "line_start": 1, "line_end": 1},
            ],
        })
        self.assertEqual({item.status for item in result.evidence}, {"confirmed", "inferred", "unresolved", "conflicting"})

    def test_analyze_writes_json_and_korean_report_without_changing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root)
            before = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True)
            output_parent = root / "outputs"
            output_parent.mkdir()
            output = output_parent / "analysis"
            result = analyze(repo, output, Planner([
                {"tool": "search_text", "args": {"pattern": "PORT"}},
                {"stop": True},
            ]))
            self.assertEqual(result.status, "complete")
            self.assertTrue((output / "analysis-result.json").is_file())
            self.assertTrue((output / "analysis-report.md").is_file())
            loaded = AnalysisResult.model_validate(json.loads((output / "analysis-result.json").read_text(encoding="utf-8")))
            self.assertEqual(loaded.status, "complete")
            self.assertIn("분석", (output / "analysis-report.md").read_text(encoding="utf-8"))
            after = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True)
            self.assertEqual(before, after)
            self.assertNotIn("top-secret", (output / "analysis-result.json").read_text(encoding="utf-8"))

    def test_analysis_result_rejects_invalid_status_with_pydantic(self):
        self.assertTrue(PYDANTIC_AVAILABLE)
        with self.assertRaises(ValueError):
            AnalysisResult.model_validate({"status": "unknown", "summary": "ok", "evidence": []})

    def test_missing_pydantic_cannot_validate_successfully(self):
        probe = (
            "from migration_assistant.analysis import AnalysisResult, PydanticDependencyError, PYDANTIC_AVAILABLE; "
            "assert not PYDANTIC_AVAILABLE; "
            "\ntry: AnalysisResult.model_validate({'status': 'complete', 'summary': 'ok', 'evidence': []})\n"
            "except PydanticDependencyError: print('blocked')"
        )
        completed = subprocess.run(
            [sys.executable, "-S", "-c", probe],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "blocked")

    def test_partial_and_failed_statuses_are_honest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root)
            output_parent = root / "outputs"
            output_parent.mkdir()
            partial = analyze(repo, output_parent / "partial", Planner([{ "tool": "list_tree", "args": {}}]), max_iterations=1)
            self.assertEqual(partial.status, "partial")
            self.assertEqual(main(["analyze", str(repo), "--output", str(output_parent / "cli")], planner=Planner([{ "stop": True }])), 2)

    def test_complete_without_evidence_is_downgraded_to_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root)
            result = analyze(repo, root / "outputs" / "no-evidence", Planner([{ "stop": True }]))

            self.assertEqual(result.status, "partial")
            self.assertTrue(any("근거" in error for error in result.errors))

    def test_analysis_does_not_consume_git_internal_files_as_repository_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root)
            (repo / ".git" / "large.pack").write_bytes(b"x" * (11 * 1024 * 1024))
            output_parent = root / "outputs"
            output_parent.mkdir()
            result = analyze(repo, output_parent / "git-filtered", Planner([{ "stop": True }]))
            self.assertEqual(result.status, "partial")


if __name__ == "__main__":
    unittest.main()
