import importlib.util
import io
import unittest
from contextlib import contextmanager
from pathlib import Path


RUNNER_PATH = Path(__file__).parents[1] / ".codex" / "code_review_graph_hook.py"
SPEC = importlib.util.spec_from_file_location("code_review_graph_hook", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class CodeReviewGraphHookTests(unittest.TestCase):
    def test_hook_drains_stdin_and_skips_when_graph_is_missing(self):
        with self._temporary_repo() as temp_dir:
            payload = io.BytesIO(b'{"tool_name":"Write","large":"payload"}')

            result = runner.main(["--repo", temp_dir], stdin=payload)

            self.assertEqual(result, 0)
            self.assertEqual(payload.read(), b"")

    def test_hook_returns_zero_when_an_update_is_already_running(self):
        with self._temporary_repo() as temp_dir:
            repo = Path(temp_dir)
            graph_dir = repo / ".code-review-graph"
            graph_dir.mkdir()
            (graph_dir / "graph.db").touch()
            lock_path = graph_dir / runner.LOCK_FILENAME
            lock_path.touch()

            result = runner.main(["--repo", temp_dir], stdin=io.BytesIO(b"{}"))

            self.assertEqual(result, 0)
            self.assertTrue(lock_path.exists())

    def test_worker_returns_zero_and_releases_lock_when_crg_fails(self):
        with self._temporary_repo() as temp_dir:
            repo = Path(temp_dir)
            graph_dir = repo / ".code-review-graph"
            graph_dir.mkdir()
            lock_path = graph_dir / runner.LOCK_FILENAME
            lock_path.touch()

            result = runner.main(
                [
                    "--worker",
                    "--repo",
                    temp_dir,
                    "--crg-executable",
                    str(repo / "missing-code-review-graph.exe"),
                ],
                stdin=io.BytesIO(b""),
            )

            self.assertEqual(result, 0)
            self.assertFalse(lock_path.exists())

    @staticmethod
    @contextmanager
    def _temporary_repo():
        base = RUNNER_PATH.parents[1] / "tests" / "fixtures" / "code_review_graph_hook"
        repo = base / "runtime"
        repo.mkdir(exist_ok=True)
        graph_dir = repo / ".code-review-graph"
        if graph_dir.exists():
            for child in graph_dir.iterdir():
                child.unlink()
            graph_dir.rmdir()
        try:
            yield str(repo)
        finally:
            if graph_dir.exists():
                for child in graph_dir.iterdir():
                    child.unlink()
                graph_dir.rmdir()


if __name__ == "__main__":
    unittest.main()
