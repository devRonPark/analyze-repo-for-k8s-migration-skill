from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from migration_assistant.repository_tools import (
    PUBLIC_TOOL_NAMES,
    RepositoryToolError,
    RepositoryTools,
    ToolBudget,
)


class RepositoryToolsTests(unittest.TestCase):
    def make_repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir()
        result = subprocess.run(["git", "init", "--quiet", str(repo)], check=False)
        self.assertEqual(result.returncode, 0)
        (repo / "app.py").write_text("PORT = 8080\nAPI_KEY = super-secret\n", encoding="utf-8")
        (repo / "notes.txt").write_text("PORT appears here\n", encoding="utf-8")
        return repo

    def test_exposes_exactly_eight_observation_tools(self):
        self.assertEqual(
            PUBLIC_TOOL_NAMES,
            (
                "inspect_target", "list_tree", "find_files", "search_text",
                "read_file", "read_file_lines", "inspect_git_metadata", "validate_analysis",
            ),
        )

    def test_search_and_line_reads_return_repository_relative_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = RepositoryTools(self.make_repo(Path(tmp)))
            hits = tools.search_text("PORT")
            self.assertEqual({hit["path"] for hit in hits}, {"app.py", "notes.txt"})
            self.assertEqual(tools.read_file_lines("app.py", 1, 1)[0]["path"], "app.py")
            with self.assertRaises(RepositoryToolError):
                tools.read_file_lines("app.py", 0, 1)

    def test_secret_values_are_redacted_and_binary_is_not_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            (repo / "binary.bin").write_bytes(b"\x00secret")
            tools = RepositoryTools(repo)
            self.assertNotIn("super-secret", tools.read_file("app.py"))
            self.assertEqual(tools.read_file("binary.bin")["binary"], True)

    def test_path_escape_and_file_budget_are_rejected_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            tools = RepositoryTools(repo, ToolBudget(max_file_size_bytes=2))
            with self.assertRaises(RepositoryToolError):
                tools.read_file("../outside.txt")
            with self.assertRaises(RepositoryToolError):
                tools.read_file("app.py")
            self.assertEqual((repo / "app.py").read_text(encoding="utf-8").splitlines()[0], "PORT = 8080")

    def test_validate_analysis_reports_invalid_evidence_without_conclusions(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = RepositoryTools(self.make_repo(Path(tmp)))
            result = tools.validate_analysis({"evidence": [{"path": "missing.py", "line_start": 1, "line_end": 1}]})
            self.assertFalse(result["valid"])
            self.assertIn("missing.py", result["errors"][0])


if __name__ == "__main__":
    unittest.main()
