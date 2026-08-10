"""The trusted control-plane context (analysis_id/revision/transition_token)
is server-owned: the model never receives it as a request field and cannot
corrupt it. See docs/development/tickets/VS-030-mid-stage-retry-exhaustion-pipeline-exit.md
for the live-run failure this closes.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from analysis_pipeline.mcp_server import Server
from analysis_pipeline.protocol import TOOLS


class ServerOwnedControlPlaneTests(unittest.TestCase):
    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temporary = tempfile.TemporaryDirectory(dir=Path(os.environ["SystemRoot"]) / "Temp")
        command_directory = Path(temporary.name) / "command"
        target = command_directory / "external-target"
        target.mkdir(parents=True)
        (target / "Dockerfile").write_text("FROM python:3.13\nCMD [\"python\", \"app.py\"]\n", encoding="utf-8")
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

    @staticmethod
    def discovery_payload(observation_ref: str) -> dict:
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

    @staticmethod
    def execution_payload(observation_ref: str, discovery_fact_refs: list[str]) -> dict:
        return {
            "schema_version": 1,
            "stage": "execution",
            "evidence": [{"alias": "runtime", "observation_ref": observation_ref}],
            "claims": [{"id": "claim-process", "status": "confirmed", "evidence_aliases": ["runtime"]}],
            "rule_applications": [],
            "discovery_fact_refs": discovery_fact_refs,
            "runtime_processes": [{
                "candidate_ids": ["candidate-web"],
                "role": "unknown",
                "execution_pattern": "unknown",
                "semantic_fact_refs": [],
            }],
        }

    def test_public_schemas_no_longer_require_control_plane_fields(self) -> None:
        by_name = {tool["name"]: tool for tool in TOOLS}
        for stage in ("discovery", "execution", "relationships", "boundaries", "contracts"):
            schema = by_name[f"submit_{stage}"]["inputSchema"]
            self.assertEqual(schema["required"], ["payload"])
            self.assertEqual(set(schema["properties"]), {"payload"})
        reopen_schema = by_name["reopen_analysis"]["inputSchema"]
        self.assertEqual(reopen_schema["required"], ["stage", "reason"])
        self.assertEqual(set(reopen_schema["properties"]), {"stage", "reason"})
        finalize_schema = by_name["finalize_analysis"]["inputSchema"]
        self.assertEqual(finalize_schema["required"], [])
        self.assertEqual(finalize_schema["properties"], {})

    def test_payload_only_flow_advances_through_discovery_and_execution(self) -> None:
        temporary, server = self.started()
        with temporary:
            discovery_observation, failed = server.tool_call("read_evidence", {"path": "Dockerfile"})
            self.assertFalse(failed, discovery_observation)
            discovery, failed = server.tool_call(
                "submit_discovery", {"payload": self.discovery_payload(discovery_observation["observation_ref"])}
            )
            self.assertFalse(failed, discovery)
            self.assertEqual(discovery["next_skill"], "analyze-k8s-execution")

            execution_observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, execution_observation)
            execution, failed = server.tool_call(
                "submit_execution",
                {
                    "payload": self.execution_payload(
                        execution_observation["observation_ref"], discovery["stage_input"]["discovery_fact_refs"]
                    )
                },
            )

        self.assertFalse(failed, execution)
        self.assertEqual(execution["next_skill"], "analyze-k8s-relationships")

    def test_successful_transitions_rotate_internal_state_the_client_never_supplied(self) -> None:
        temporary, server = self.started()
        with temporary:
            initial_revision, initial_token = server.session.revision, server.session.transition_token
            observation, failed = server.tool_call("read_evidence", {"path": "Dockerfile"})
            self.assertFalse(failed, observation)
            discovery, failed = server.tool_call(
                "submit_discovery", {"payload": self.discovery_payload(observation["observation_ref"])}
            )

        self.assertFalse(failed, discovery)
        self.assertEqual(server.session.revision, initial_revision + 1)
        self.assertNotEqual(server.session.transition_token, initial_token)
        self.assertEqual(server.session.current_stage, "execution")

    def test_failed_submission_does_not_mutate_active_analysis_state(self) -> None:
        temporary, server = self.started()
        with temporary:
            revision_before, stage_before, token_before = (
                server.session.revision, server.session.current_stage, server.session.transition_token
            )
            rejected, failed = server.tool_call(
                "submit_discovery", {"payload": self.discovery_payload("nonexistent_observation_ref")}
            )

        self.assertTrue(failed, rejected)
        self.assertEqual(server.session.revision, revision_before)
        self.assertEqual(server.session.current_stage, stage_before)
        self.assertEqual(server.session.transition_token, token_before)

    def test_out_of_order_submit_is_rejected(self) -> None:
        temporary, server = self.started()
        with temporary:
            result, failed = server.tool_call(
                "submit_execution",
                {"payload": self.execution_payload("whatever", [])},
            )

        self.assertTrue(failed)
        self.assertEqual(result["code"], "stage_order")
        self.assertEqual(server.session.current_stage, "discovery")

    def test_finalize_and_reopen_take_no_control_plane_arguments(self) -> None:
        temporary, server = self.started()
        with temporary:
            # finalize_analysis is called before the pipeline reaches "finalize";
            # the point here is only that it requires no request fields at all,
            # not that this particular call succeeds.
            finalize_result, finalize_failed = server.tool_call("finalize_analysis", {})
            reopen_result, reopen_failed = server.tool_call(
                "reopen_analysis", {"stage": "discovery", "reason": "confused"}
            )

        self.assertTrue(finalize_failed)
        self.assertEqual(finalize_result["code"], "stage_order")
        self.assertTrue(reopen_failed)
        self.assertEqual(reopen_result["code"], "reopen_not_ready")

    def test_client_supplied_control_plane_fields_are_ignored_not_consulted(self) -> None:
        # The exact live-run failure this closes: a model that invents or
        # corrupts an analysis_id/revision/transition_token can no longer
        # target a different (or nonexistent) analysis, because the server
        # never reads those fields from the request in the first place.
        temporary, server = self.started()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "Dockerfile"})
            self.assertFalse(failed, observation)
            forged_arguments = {
                "analysis_id": "an_invented_by_the_model",
                "revision": 999,
                "transition_token": "tr_invented_by_the_model",
                "payload": self.discovery_payload(observation["observation_ref"]),
            }
            result, failed = server.tool_call("submit_discovery", forged_arguments)

        self.assertFalse(failed, result)
        self.assertEqual(result["analysis_id"], server.session.analysis_id)
        self.assertNotEqual(result["analysis_id"], "an_invented_by_the_model")


if __name__ == "__main__":
    unittest.main()
