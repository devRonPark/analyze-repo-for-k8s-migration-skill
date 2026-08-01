from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from migration_assistant.target import (
    BudgetExceededError,
    SafetyBudget,
    TargetSafetyError,
    TargetSafetyGate,
)


class TargetSafetyTests(unittest.TestCase):
    def make_repo(self, parent: Path, name: str = "repo") -> Path:
        repo = parent / name
        repo.mkdir()
        result = subprocess.run(
            ["git", "init", "--quiet", str(repo)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        (repo / "README.md").write_text("safe\n", encoding="utf-8")
        return repo

    def test_resolves_canonical_git_repository_without_mutating_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root)
            before = (repo / "README.md").read_bytes()
            status_before = subprocess.run(
                ["git", "-C", str(repo), "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=False,
            )

            gate = TargetSafetyGate.open(repo)
            self.assertEqual(gate.repository, repo.resolve())
            list(gate.iter_files())
            self.assertEqual(gate.read_file(Path("README.md")), before)

            status_after = subprocess.run(
                ["git", "-C", str(repo), "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(status_after.returncode, status_before.returncode)
            self.assertEqual(status_after.stdout, status_before.stdout)
            self.assertEqual((repo / "README.md").read_bytes(), before)

    def test_rejects_directory_that_is_not_a_git_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain = Path(tmp) / "plain"
            plain.mkdir()
            with self.assertRaisesRegex(TargetSafetyError, "Git repository"):
                TargetSafetyGate.open(plain)

    def test_rejects_existing_output_even_when_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root)
            output = root / "existing-output"
            output.mkdir()

            with self.assertRaisesRegex(TargetSafetyError, "이미 존재"):
                TargetSafetyGate.open(repo, output).create_output()
            self.assertTrue(output.is_dir())
            self.assertEqual(list(output.iterdir()), [])

    def test_rejects_output_inside_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root)
            output = repo / "artifacts"

            with self.assertRaisesRegex(TargetSafetyError, "Repository 내부"):
                TargetSafetyGate.open(repo, output)
            self.assertFalse(output.exists())

    def test_rejects_output_path_that_contains_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_parent = root / "container"
            output_parent.mkdir()
            repo = self.make_repo(output_parent)
            output = output_parent / "new-output"

            with self.assertRaisesRegex(TargetSafetyError, "포함"):
                TargetSafetyGate.open(repo, output)
            self.assertFalse(output.exists())

    def test_rejects_symlink_escape_during_repository_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root)
            outside = root / "outside"
            outside.mkdir()
            (outside / "secret.txt").write_text("not in repo\n", encoding="utf-8")
            link = repo / "linked-outside"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlink 생성 권한 없음: {error}")

            gate = TargetSafetyGate.open(repo)
            with self.assertRaisesRegex(TargetSafetyError, "symlink|junction"):
                list(gate.iter_files())

    def test_enforces_file_exploration_and_iteration_budgets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root)
            (repo / "large.bin").write_bytes(b"0123456789")
            (repo / "second.txt").write_text("second\n", encoding="utf-8")
            budget = SafetyBudget(
                max_file_size_bytes=5,
                max_files=1,
                max_explorations=1,
                max_iterations=1,
            )
            gate = TargetSafetyGate.open(repo, budget=budget)

            with self.assertRaises(BudgetExceededError):
                gate.read_file("large.bin")
            with self.assertRaises(BudgetExceededError):
                list(gate.iter_files())
            gate.consume_exploration()
            with self.assertRaises(BudgetExceededError):
                gate.consume_exploration()
            gate.consume_iteration()
            with self.assertRaises(BudgetExceededError):
                gate.consume_iteration()

    def test_default_output_is_exclusive_sibling_and_cleanup_is_transactional(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root)
            gate = TargetSafetyGate.open(repo)
            transaction = gate.create_output()
            self.assertEqual(transaction.path.parent, repo.resolve().parent)
            self.assertFalse(transaction.path == repo.resolve())
            transaction.path.joinpath("partial.txt").write_text("partial\n", encoding="utf-8")
            transaction.cleanup()
            self.assertFalse(transaction.path.exists())

            committed = gate.create_output()
            committed.path.joinpath("result.txt").write_text("complete\n", encoding="utf-8")
            committed.mark_complete()
            committed.cleanup()
            self.assertTrue(committed.path.exists())
            self.assertEqual(committed.path.joinpath("result.txt").read_text(encoding="utf-8"), "complete\n")

    def test_cleanup_does_not_remove_preexisting_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root)
            existing = root / "existing"
            existing.mkdir()
            marker = existing / "marker.txt"
            marker.write_text("keep\n", encoding="utf-8")

            with self.assertRaises(TargetSafetyError):
                TargetSafetyGate.open(repo, existing).create_output()
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep\n")


if __name__ == "__main__":
    unittest.main()
