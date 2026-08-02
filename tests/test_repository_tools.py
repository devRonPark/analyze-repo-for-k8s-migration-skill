from __future__ import annotations

import subprocess
import tempfile
import unittest
import os
from pathlib import Path

from migration_assistant.repository_tools import (
    PUBLIC_TOOL_NAMES,
    RepositoryToolError,
    RepositoryTools,
    ToolBudget,
)
from migration_assistant.target import BudgetExceededError


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
            hits = tools.search_text("PORT")["hits"]
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

    def test_all_repository_file_tools_reject_git_internal_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            (repo / ".gitignore").write_text("build/\n", encoding="utf-8")
            tools = RepositoryTools(repo)
            self.assertFalse(tools.read_file(".gitignore")["binary"])
            for operation in (
                lambda: tools.list_tree(".git"),
                lambda: tools.find_files(".git/*"),
                lambda: tools.search_text("config", ".git"),
                lambda: tools.read_file(".git/config"),
                lambda: tools.read_file_lines(".git/config", 1, 1),
            ):
                with self.subTest(operation=operation):
                    with self.assertRaises(RepositoryToolError):
                        operation()

    def test_git_component_normalization_is_case_insensitive_before_filesystem_access(self):
        for value in (".git", ".GIT", ".Git", "foo/../.GIT/config"):
            with self.subTest(value=value):
                self.assertTrue(RepositoryTools._contains_git_component(value))

    def test_canonical_git_directory_and_symlink_alias_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            tools = RepositoryTools(repo)
            with self.assertRaises(RepositoryToolError):
                tools.read_file("foo/../.GIT/config")
            alias = repo / "git-alias"
            try:
                os.symlink(repo / ".git", alias, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("filesystem does not permit symlink creation")
            with self.assertRaises(RepositoryToolError):
                tools.read_file("git-alias/config")

    def test_validate_analysis_rechecks_actual_excerpt_and_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = RepositoryTools(self.make_repo(Path(tmp)))
            base = {
                "status": "complete",
                "summary": "애플리케이션의 runtime 사실",
                "findings": [{"id": "f1", "status": "confirmed", "claim": "PORT 설정이 확인됨", "evidence_ids": ["e1"]}],
                "evidence": [{"id": "e1", "status": "confirmed", "path": "app.py", "line_start": 1, "line_end": 1, "claim": "PORT 설정이 확인됨", "text": "PORT = 8080"}],
                "iterations": 1,
                "errors": [],
                "termination": "normal",
            }
            self.assertTrue(tools.validate_analysis(base)["valid"])
            for key, value in (("path", "missing.py"), ("line_start", 99), ("text", "not in repository"), ("claim", "")):
                invalid = {**base, "evidence": [{**base["evidence"][0], key: value}]}
                with self.subTest(key=key):
                    self.assertFalse(tools.validate_analysis(invalid)["valid"])

    def test_external_decision_is_structured_and_not_a_process_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = RepositoryTools(self.make_repo(Path(tmp)))
            candidate = {
                "status": "complete",
                "summary": "Repository 분석",
                "findings": [
                    {"id": "f1", "status": "confirmed", "claim": "PORT 설정이 확인됨", "evidence_ids": ["e1"]},
                    {"id": "f2", "status": "unresolved", "claim": "배포 환경 선택이 필요함", "evidence_ids": [], "resolution_owner": "deployment_environment", "resolution_source": "deployment decision", "reason": "Repository가 결정하지 않음"},
                ],
                "evidence": [{"id": "e1", "status": "confirmed", "path": "app.py", "line_start": 1, "line_end": 1, "claim": "PORT 설정이 확인됨", "text": "PORT = 8080"}],
                "iterations": 1,
                "errors": [],
                "termination": "normal",
            }
            self.assertTrue(tools.validate_analysis(candidate)["valid"])
            self.assertFalse(tools.validate_analysis({**candidate, "errors": ["외부 배포 선택이 남아 있음"]})["valid"])

    def test_search_result_cap_exposes_truncation_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = RepositoryTools(self.make_repo(Path(tmp)), ToolBudget(max_search_results=1))

            result = tools.search_text("PORT")

            self.assertEqual(result["returned_hit_count"], 1)
            self.assertEqual(result["hit_count"], 2)
            self.assertTrue(result["truncated"])

    def test_total_byte_budget_is_shared_by_file_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = RepositoryTools(self.make_repo(Path(tmp)), ToolBudget(max_total_bytes=1))
            with self.assertRaises(BudgetExceededError):
                tools.read_file("app.py")

    def test_file_response_is_truncated_by_shared_context_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            (repo / "large.txt").write_text("x" * 20, encoding="utf-8")
            tools = RepositoryTools(repo, ToolBudget(max_tool_response_bytes=5))
            result = tools.read_file("large.txt")
            self.assertTrue(result["truncated"])
            self.assertLessEqual(result["returned_bytes"], 5)


if __name__ == "__main__":
    unittest.main()
