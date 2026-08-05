from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path


class TempfileSandboxTests(unittest.TestCase):
    def test_nested_fixture_directory_is_worktree_local_and_cleanable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "repository"
            nested.mkdir()
            (nested / "app.py").write_text("PORT = 8080\n", encoding="utf-8")

            self.assertFalse(root.is_relative_to(Path.cwd()))
            self.assertEqual((nested / "app.py").read_text(encoding="utf-8"), "PORT = 8080\n")

        self.assertFalse(root.exists())

    def test_stdlib_arguments_and_mkdtemp_are_preserved(self):
        with tempfile.TemporaryDirectory(prefix="fixture-", suffix="-repo") as tmp:
            self.assertTrue(Path(tmp).name.startswith("fixture-"))
            self.assertTrue(Path(tmp).name.endswith("-repo"))

        root = Path(tempfile.mkdtemp(prefix="explicit-", suffix="-root", dir=tempfile.gettempdir()))
        try:
            self.assertTrue(root.name.startswith("explicit-"))
            self.assertTrue(root.name.endswith("-root"))
        finally:
            shutil.rmtree(root, ignore_errors=False)

    @unittest.skipUnless(sys.version_info >= (3, 12), "TemporaryDirectory(delete=...) requires Python 3.12+")
    def test_delete_false_leaves_directory_until_explicit_cleanup(self):
        with tempfile.TemporaryDirectory(delete=False) as tmp:
            root = Path(tmp)
            (root / "fixture.txt").write_text("kept", encoding="utf-8")

        self.assertTrue(root.exists())
        shutil.rmtree(root, ignore_errors=False)
        self.assertFalse(root.exists())
