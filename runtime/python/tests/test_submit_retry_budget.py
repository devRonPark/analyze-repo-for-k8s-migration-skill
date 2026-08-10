import os
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from analysis_pipeline.mcp_server import Server


class SubmitRetryBudgetTests(unittest.TestCase):
    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temporary = tempfile.TemporaryDirectory(dir=Path(os.environ["SystemRoot"]) / "Temp")
        command_directory = Path(temporary.name) / "command"
        target = command_directory / "external-target"
        target.mkdir(parents=True)
        (target / "Dockerfile").write_text("FROM python:3.13\n", encoding="utf-8")
        subprocess.run(["git", "init"], cwd=target, check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=target, check=True, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture"],
            cwd=target,
            check=True,
            capture_output=True,
        )
        return temporary, command_directory, target

    def started(self) -> tuple[tempfile.TemporaryDirectory[str], Server, Path]:
        temporary, command_directory, target = self.fixture()
        server = Server(command_directory=command_directory)
        server.tool_call("start_analysis", {"target_path": "external-target", "mode": "summary"})
        return temporary, server, target

    @staticmethod
    def payload(observation_ref: str) -> dict:
        return {
            "schema_version": 1,
            "stage": "discovery",
            "evidence": [{"alias": "container", "observation_ref": observation_ref}],
            "claims": [{"id": "claim-container", "status": "confirmed", "evidence_aliases": ["container"]}],
            "rule_applications": [],
            "signals": ["container-runtime"],
            "candidate_ids": ["candidate-web"],
            "decisions": ["decision-runtime"],
        }

    def foreign_observation_ref(self, server: Server, target: Path) -> str:
        # An observation issued under a stage other than the current one is a
        # cheap, repeatable way to trigger a genuine payload rejection
        # ("observation stage mismatch") without needing a fresh precision
        # call — and unlike most rejection codes it is retryable=True by
        # default, which is exactly the shape the retry budget needs to cap.
        return server.session.registry.issue_present(
            "execution", target / "Dockerfile", 1, 1, "1: FROM python:3.13"
        )["observation_ref"]

    def test_top_level_contract_error_names_all_fields_and_allows_corrected_retry(self) -> None:
        temporary, server, _ = self.started()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "Dockerfile"})
            self.assertFalse(failed, observation)
            payload = self.payload(observation["observation_ref"])
            del payload["stage"]
            payload["discovery_fact_refs"] = ["invented"]
            rejected, failed = server.tool_call("submit_discovery", {"payload": payload})
            accepted, accepted_failed = server.tool_call(
                "submit_discovery", {"payload": self.payload(observation["observation_ref"])}
            )

        self.assertTrue(failed)
        self.assertEqual(rejected["code"], "invalid_stage_payload")
        self.assertTrue(rejected["retryable"])
        self.assertEqual(rejected["stage"], "discovery")
        self.assertEqual(rejected["missing_fields"], ["stage"])
        self.assertEqual(rejected["unexpected_fields"], ["discovery_fact_refs"])
        self.assertIn("stage", rejected["required_fields"])
        self.assertEqual(rejected["budget"]["submit_rejections_remaining"], 2)
        self.assertNotIn("invented", json.dumps(rejected, sort_keys=True))
        self.assertFalse(accepted_failed, accepted)
        self.assertEqual(accepted["next_skill"], "analyze-k8s-execution")

    def test_empty_discovery_evidence_has_safe_corrective_guidance(self) -> None:
        temporary, server, _ = self.started()
        with temporary:
            payload = self.payload("not-used")
            payload["evidence"] = []
            rejected, failed = server.tool_call("submit_discovery", {"payload": payload})

        self.assertTrue(failed)
        self.assertEqual(rejected["code"], "invalid_stage_payload")
        self.assertTrue(rejected["retryable"])
        self.assertEqual(rejected["stage"], "discovery")
        self.assertIn("stage_input.survey", rejected["issues"][0])
        self.assertNotIn("not-used", json.dumps(rejected, sort_keys=True))

    def test_first_three_rejections_stay_retryable(self) -> None:
        temporary, server, target = self.started()
        with temporary:
            results = []
            for _ in range(3):
                ref = self.foreign_observation_ref(server, target)
                result, failed = server.tool_call(
                    "submit_discovery", {"payload": self.payload(ref)}
                )
                results.append((result, failed))

        for result, failed in results:
            self.assertTrue(failed)
            self.assertEqual(result["code"], "observation_stage_mismatch")
            self.assertTrue(result["retryable"])

    def test_fourth_rejection_becomes_non_retryable_with_a_budget_note(self) -> None:
        temporary, server, target = self.started()
        with temporary:
            for _ in range(3):
                ref = self.foreign_observation_ref(server, target)
                server.tool_call("submit_discovery", {"payload": self.payload(ref)})
            ref = self.foreign_observation_ref(server, target)
            fourth, fourth_failed = server.tool_call(
                "submit_discovery", {"payload": self.payload(ref)}
            )
            fifth, fifth_failed = server.tool_call(
                "submit_discovery", {"payload": self.payload(ref)}
            )

        self.assertTrue(fourth_failed)
        self.assertEqual(fourth["code"], "observation_stage_mismatch")
        self.assertFalse(fourth["retryable"])
        self.assertIn("retry budget", fourth["issues"][0])
        self.assertTrue(fifth_failed)
        self.assertFalse(fifth["retryable"])
        self.assertEqual(server.session.current_stage, "discovery")

    def test_finalize_analysis_does_not_consume_the_submission_retry_budget(self) -> None:
        # Reproduces the live-run failure directly: submit_boundaries never
        # succeeded, so current_stage stayed "boundaries" while the model
        # called finalize_analysis repeatedly against a stage_order rejection
        # it never fixed. finalize_analysis was not covered by any budget
        # before this fix.
        temporary, server, _ = self.started()
        with temporary:
            results = [server.tool_call("finalize_analysis", {}) for _ in range(5)]

        for result, failed in results:
            self.assertTrue(failed)
            self.assertEqual(result["code"], "stage_order")
            self.assertNotIn("retry budget", result["issues"][0])
        self.assertEqual(server.session.submit_rejections, 0)

    def test_out_of_order_submit_does_not_consume_the_current_stage_budget(self) -> None:
        temporary, server, _ = self.started()
        with temporary:
            result, failed = server.tool_call("submit_execution", {"payload": {}})

        self.assertTrue(failed)
        self.assertEqual(result["code"], "stage_order")
        self.assertEqual(server.session.submit_rejections, 0)


if __name__ == "__main__":
    unittest.main()
