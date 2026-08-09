import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis_pipeline.mcp_server import Server


class PrecisionBudgetTests(unittest.TestCase):
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

    def test_start_analysis_pushes_a_bounded_discovery_survey_with_budget(self) -> None:
        temporary, command_directory, _ = self.fixture()
        with temporary:
            server = Server(command_directory=command_directory)
            handoff, failed = server.tool_call("start_analysis", {"target_path": "external-target", "mode": "summary"})

        self.assertFalse(failed, handoff)
        survey = handoff["stage_input"]["survey"]
        self.assertEqual(survey["stage"], "discovery")
        self.assertTrue(survey["surveyed"])
        self.assertLessEqual(len(survey["observations"]), 12)
        self.assertEqual(
            handoff["stage_input"]["budget"],
            {"precision_calls_remaining": 1, "submit_rejections_remaining": 3},
        )

    def test_first_precision_call_succeeds_second_is_a_terminal_error(self) -> None:
        temporary, server = self.started()
        with temporary:
            first, first_failed = server.tool_call("read_evidence", {"path": "app.py"})
            second, second_failed = server.tool_call("locate_evidence", {"glob": "*.py"})

        self.assertFalse(first_failed, first)
        self.assertEqual(first["budget"]["precision_calls_remaining"], 0)
        self.assertTrue(second_failed)
        self.assertEqual(second["code"], "precision_budget_exhausted")
        self.assertFalse(second["retryable"])

    def test_repeated_over_budget_calls_return_byte_identical_errors(self) -> None:
        temporary, server = self.started()
        with temporary:
            server.tool_call("read_evidence", {"path": "app.py"})
            first, first_failed = server.tool_call("list_target_paths", {"pattern": "*"})
            second, second_failed = server.tool_call("locate_evidence", {"glob": "*.py"})

        self.assertTrue(first_failed)
        self.assertTrue(second_failed)
        self.assertEqual(first, second)

    def test_git_metadata_is_not_gated_by_the_precision_budget(self) -> None:
        temporary, server = self.started()
        with temporary:
            server.tool_call("read_evidence", {"path": "app.py"})
            first, first_failed = server.tool_call("get_target_git_metadata", {})
            second, second_failed = server.tool_call("get_target_git_metadata", {})

        self.assertFalse(first_failed, first)
        self.assertFalse(second_failed, second)

    def test_budget_resets_on_stage_transition(self) -> None:
        temporary, server = self.started()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "Dockerfile"})
            self.assertFalse(failed, observation)
            exhausted, exhausted_failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertTrue(exhausted_failed)

            payload = {
                "schema_version": 1,
                "stage": "discovery",
                "evidence": [{"alias": "container", "observation_ref": observation["observation_ref"]}],
                "claims": [{"id": "claim-container", "status": "confirmed", "evidence_aliases": ["container"]}],
                "rule_applications": [],
                "signals": ["container-runtime"],
                "candidate_ids": ["candidate-web"],
                "decisions": ["decision-runtime"],
            }
            started_state = server.session
            envelope = {
                "analysis_id": started_state.analysis_id,
                "revision": started_state.revision,
                "transition_token": started_state.transition_token,
            }
            discovery, discovery_failed = server.tool_call("submit_discovery", {**envelope, "payload": payload})
            self.assertFalse(discovery_failed, discovery)
            next_call, next_failed = server.tool_call("read_evidence", {"path": "app.py"})

        self.assertFalse(next_failed, next_call)


if __name__ == "__main__":
    unittest.main()
