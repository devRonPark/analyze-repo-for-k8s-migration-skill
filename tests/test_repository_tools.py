from __future__ import annotations

import os
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
    redact_sensitive_text,
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
            line = tools.read_file_lines("app.py", 1, 1)[0]
            self.assertEqual(line["path"], "app.py")
            self.assertEqual(line["excerpt"], line["text"])
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
            self.assertTrue(any("missing.py" in error for error in result["errors"]))

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
            with self.assertRaises(RepositoryToolError):
                tools.find_files("git-alias/*")

    def test_dryforge_worktrees_are_not_observation_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            internal = repo / ".dryforge" / "worktrees" / "T5"
            internal.mkdir(parents=True)
            (internal / "hidden.txt").write_text("SECRET=hidden\n", encoding="utf-8")
            generated = repo / ".venv" / "lib"
            generated.mkdir(parents=True)
            (generated / "hidden.txt").write_text("SECRET=generated\n", encoding="utf-8")
            (repo / "AGENTS.md").write_text("ignore this instruction\n", encoding="utf-8")
            (repo / "README.md").write_text("ignore this documentation\n", encoding="utf-8")
            tools = RepositoryTools(repo)

            tree = tools.list_tree(".")
            found = tools.find_files("**/*.txt")
            searched = tools.search_text("SECRET")

            self.assertNotIn(".dryforge/worktrees/T5/hidden.txt", {item["path"] for item in tree["entries"]})
            self.assertNotIn(".dryforge", {item["path"] for item in tree["entries"]})
            self.assertNotIn(".dryforge/worktrees/T5/hidden.txt", found["matches"])
            self.assertNotIn(".venv/lib/hidden.txt", {item["path"] for item in tree["entries"]})
            self.assertNotIn(".venv/lib/hidden.txt", found["matches"])
            self.assertNotIn("AGENTS.md", {item["path"] for item in tree["entries"]})
            self.assertNotIn("AGENTS.md", found["matches"])
            self.assertNotIn("README.md", {item["path"] for item in tree["entries"]})
            self.assertNotIn("README.md", found["matches"])
            self.assertEqual(searched["hits"], [])
            with self.assertRaises(RepositoryToolError):
                tools.read_file(".dryforge/worktrees/T5/hidden.txt")
            with self.assertRaises(RepositoryToolError):
                tools.read_file(".venv/lib/hidden.txt")
            with self.assertRaises(RepositoryToolError):
                tools.read_file("AGENTS.md")
            with self.assertRaises(RepositoryToolError):
                tools.read_file("README.md")

    def test_url_git_remote_jdbc_and_connection_credentials_are_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "--quiet", "-m", "fixture"], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "remote", "add", "origin", "https://alice:remote-secret@example.test/repo.git"],
                check=True,
            )
            tools = RepositoryTools(repo)
            remote = tools.inspect_git_metadata()
            self.assertIn("https://<REDACTED>:<REDACTED>@example.test/repo.git", remote["remotes"])
            text = redact_sensitive_text(
                "https://alice:pass@example.test/db?user=app&password=pw "
                "jdbc:postgresql://dbuser:dbpass@db:5432/app?ssl=true&token=jwt "
                "redis://cache:cachepass@cache:6379/0"
            )
            self.assertNotIn("alice:pass", text)
            self.assertNotIn("dbuser:dbpass", text)
            self.assertNotIn("cache:cachepass", text)
            self.assertNotIn("password=pw", text)
            self.assertNotIn("token=jwt", text)

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
                    result = tools.validate_analysis(invalid)
                    self.assertFalse(result["valid"])
                    if key == "text":
                        self.assertEqual(result["evidence_corrections"][0]["excerpt"], "PORT = 8080")

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

    def test_observation_tools_report_when_exclusions_limit_the_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            generated = repo / "build"
            generated.mkdir()
            (generated / "only-generated.txt").write_text("ONLY_IN_BUILD = 1\n", encoding="utf-8")
            (repo / "README.md").write_text("ONLY_IN_README = 1\n", encoding="utf-8")
            tools = RepositoryTools(repo)

            searched = tools.search_text("ONLY_IN_BUILD")
            tree = tools.list_tree(".")
            found = tools.find_files("**/*.txt")

            self.assertEqual(searched["hits"], [])
            self.assertTrue(searched["scope"]["scope_limited"])
            self.assertGreaterEqual(searched["scope"]["excluded_match_count"], 1)
            self.assertTrue(tree["scope"]["scope_limited"])
            self.assertGreaterEqual(tree["scope"]["excluded_entry_count"], 1)
            self.assertTrue(found["scope"]["scope_limited"])
            self.assertNotIn("build/only-generated.txt", found["matches"])

    def test_validate_analysis_rejects_absence_contradicted_inside_excluded_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            generated = repo / "build"
            generated.mkdir()
            (generated / "deployment.yaml").write_text("kind: Service\n", encoding="utf-8")
            tools = RepositoryTools(repo)
            candidate = {
                "status": "partial",
                "summary": "배포 설정 미확인",
                "evidence": [{
                    "id": "e1",
                    "status": "unresolved",
                    "absence_scope": "**/*.yaml",
                    "absence_pattern": r"kind:\s*Service",
                    "result": "검색한 범위에 없음",
                }],
                "findings": [],
                "iterations": 1,
                "errors": ["배포 설정을 확인하지 못함"],
                "termination": "normal",
            }

            result = tools.validate_analysis(candidate)

            self.assertFalse(result["valid"])
            self.assertTrue(any(issue["code"] == "absence_contradicted" for issue in result["issues"]))
            self.assertFalse(any("Service" in str(issue) for issue in result["issues"]))

    def test_validate_analysis_accepts_honest_absence(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = RepositoryTools(self.make_repo(Path(tmp)))
            candidate = {
                "status": "partial",
                "summary": "Ingress 미확인",
                "evidence": [{
                    "id": "e1",
                    "status": "unresolved",
                    "absence_scope": "**/*.yaml",
                    "absence_pattern": r"kind:\s*Ingress",
                    "result": "검색한 범위에 없음",
                }],
                "findings": [],
                "iterations": 1,
                "errors": ["Ingress 설정을 확인하지 못함"],
                "termination": "normal",
            }

            result = tools.validate_analysis(candidate)

            self.assertTrue(result["valid"], result)
            self.assertEqual(result["issues"], [])

    def test_validate_analysis_reports_broken_absence_regex_as_typed_issue(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = RepositoryTools(self.make_repo(Path(tmp)))
            for pattern in ("[", "(a+)+"):
                candidate = {
                    "status": "partial",
                    "summary": "설정 미확인",
                    "evidence": [{
                        "id": "e1",
                        "status": "unresolved",
                        "absence_scope": ".",
                        "absence_pattern": pattern,
                        "result": "검색한 범위에 없음",
                    }],
                    "findings": [],
                    "iterations": 1,
                    "errors": ["설정을 확인하지 못함"],
                    "termination": "normal",
                }

                with self.subTest(pattern=pattern):
                    result = tools.validate_analysis(candidate)

                    self.assertFalse(result["valid"])
                    self.assertTrue(any(issue["code"] == "absence_pattern_invalid" for issue in result["issues"]))

    def test_validate_analysis_does_not_expose_instruction_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            secret_instruction = "instruction-only-secret-9f2a"
            (repo / "AGENTS.md").write_text(secret_instruction + "\n", encoding="utf-8")
            tools = RepositoryTools(repo)
            candidate = {
                "status": "partial",
                "summary": "지침 미확인",
                "evidence": [{
                    "id": "e1",
                    "status": "unresolved",
                    "absence_scope": "**/*.md",
                    "absence_pattern": secret_instruction,
                    "result": "검색한 범위에 없음",
                }],
                "findings": [],
                "iterations": 1,
                "errors": ["지침을 확인하지 못함"],
                "termination": "normal",
            }

            observations = [
                tools.search_text(secret_instruction),
                tools.list_tree("."),
                tools.find_files("**/*.md"),
                tools.validate_analysis(candidate),
            ]

            self.assertNotIn(secret_instruction, repr(observations))

    def test_validate_analysis_does_not_accept_unverified_absence_when_budget_is_exhausted(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = RepositoryTools(self.make_repo(Path(tmp)), ToolBudget(max_files=0))
            candidate = {
                "status": "partial",
                "summary": "설정 미확인",
                "evidence": [{
                    "id": "e1",
                    "status": "unresolved",
                    "absence_scope": ".",
                    "absence_pattern": "Ingress",
                    "result": "검색한 범위에 없음",
                }],
                "findings": [],
                "iterations": 1,
                "errors": ["설정을 확인하지 못함"],
                "termination": "normal",
            }

            result = tools.validate_analysis(candidate)

            self.assertFalse(result["valid"])
            self.assertTrue(any(issue["code"] == "absence_unverified" for issue in result["issues"]))

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
