import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis_pipeline.mcp_server import Server


class EvidenceAccessTests(unittest.TestCase):
    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temporary = tempfile.TemporaryDirectory(dir=Path(os.environ["SystemRoot"]) / "Temp")
        command_directory = Path(temporary.name) / "command"
        target = command_directory / "external-target"
        target.mkdir(parents=True)
        (target / "Dockerfile").write_text("FROM python:3.13\n", encoding="utf-8")
        (target / "app.py").write_text("print('ready')\n", encoding="utf-8")
        subprocess.run(["git", "init"], cwd=target, check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=target, check=True, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture"],
            cwd=target,
            check=True,
            capture_output=True,
        )
        return temporary, command_directory, target

    def started(self) -> tuple[tempfile.TemporaryDirectory[str], Server]:
        temporary, command_directory, _ = self.fixture()
        server = Server(command_directory=command_directory)
        server.tool_call("start_analysis", {"target_path": "external-target", "mode": "summary"})
        return temporary, server

    def test_stage_handoff_exposes_only_submit_retry_budget(self) -> None:
        temporary, command_directory, _ = self.fixture()
        with temporary:
            server = Server(command_directory=command_directory)
            handoff, failed = server.tool_call("start_analysis", {"target_path": "external-target", "mode": "summary"})

        self.assertFalse(failed, handoff)
        self.assertEqual(handoff["stage_input"]["budget"], {"submit_rejections_remaining": 3})

    def test_repeated_target_reads_are_not_budget_gated(self) -> None:
        temporary, server = self.started()
        with temporary:
            first, first_failed = server.tool_call("read_evidence", {"path": "app.py"})
            second, second_failed = server.tool_call("locate_evidence", {"glob": "Dockerfile"})
            third, third_failed = server.tool_call("list_target_paths", {"pattern": "*.py"})

        self.assertFalse(first_failed, first)
        self.assertFalse(second_failed, second)
        self.assertFalse(third_failed, third)
        self.assertEqual(first["budget"], {"submit_rejections_remaining": 3})
        self.assertEqual(second["budget"], {"submit_rejections_remaining": 3})
        self.assertEqual(third["budget"], {"submit_rejections_remaining": 3})

    def test_git_metadata_remains_read_only_and_ungated(self) -> None:
        temporary, server = self.started()
        with temporary:
            server.tool_call("read_evidence", {"path": "app.py"})
            metadata, failed = server.tool_call("get_target_git_metadata", {})

        self.assertFalse(failed, metadata)
        self.assertEqual(metadata["budget"], {"submit_rejections_remaining": 3})


if __name__ == "__main__":
    unittest.main()
