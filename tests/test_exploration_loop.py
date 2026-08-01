from __future__ import annotations

import tempfile
import unittest
import subprocess
from pathlib import Path

from migration_assistant.exploration import ExplorationLoop, ExplorationStatus
from migration_assistant.repository_tools import RepositoryTools


class Planner:
    def __init__(self, actions):
        self.actions = iter(actions)

    def next_action(self, observation):
        return next(self.actions)


class ExplorationLoopTests(unittest.TestCase):
    def make_repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
        (repo / "app.txt").write_text("PORT=8080\nTOKEN=top-secret\n", encoding="utf-8")
        return repo

    def test_planner_selects_generic_tools_and_stop_is_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = RepositoryTools(self.make_repo(Path(tmp)))
            planner = Planner([
                {"tool": "search_text", "args": {"pattern": "PORT"}},
                {"stop": True},
            ])
            result = ExplorationLoop(tools, planner, max_iterations=3).run()
            self.assertEqual(result.status, ExplorationStatus.COMPLETE)
            self.assertEqual(result.iterations, 2)
            self.assertEqual(result.evidence[0].path, "app.txt")

    def test_iteration_limit_returns_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = RepositoryTools(self.make_repo(Path(tmp)))
            planner = Planner([{ "tool": "list_tree", "args": {}}])
            result = ExplorationLoop(tools, planner, max_iterations=1).run()
            self.assertEqual(result.status, ExplorationStatus.PARTIAL)
            self.assertTrue(any("iteration" in error for error in result.errors))

    def test_unresolved_and_conflicting_evidence_stay_separate_and_secret_is_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = RepositoryTools(self.make_repo(Path(tmp)))
            planner = Planner([
                {"tool": "read_file", "args": {"relative": "app.txt"}, "status": "unresolved"},
                {"tool": "read_file_lines", "args": {"relative": "app.txt", "line_start": 1, "line_end": 1}, "status": "conflicting"},
                {"stop": True},
            ])
            result = ExplorationLoop(tools, planner, max_iterations=3).run()
            self.assertEqual({item.status for item in result.evidence}, {"unresolved", "conflicting"})
            self.assertNotIn("top-secret", repr(result))

    def test_non_observation_tool_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = RepositoryTools(self.make_repo(Path(tmp)))
            result = ExplorationLoop(tools, Planner([{ "tool": "render_manifests", "args": {}}]), max_iterations=1).run()
            self.assertEqual(result.status, ExplorationStatus.PARTIAL)
            self.assertIn("공개되지 않은", result.errors[0])


if __name__ == "__main__":
    unittest.main()
