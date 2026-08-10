import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from analysis_pipeline.mcp_server import Server


class DiscoveryStageTests(unittest.TestCase):
    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        # The analysis target must be outside the Skill installation. The
        # repository-local test temporary directory intentionally exercises
        # the server's installation-root rejection, so use Windows' temp root
        # for this external-target fixture.
        temporary = tempfile.TemporaryDirectory(dir=Path(os.environ["SystemRoot"]) / "Temp")
        command_directory = Path(temporary.name) / "command"
        target = command_directory / "external-target"
        target.mkdir(parents=True)
        (target / "Dockerfile").write_text("FROM python:3.13\nCMD [\"python\", \"app.py\"]\n", encoding="utf-8")
        (target / "settings.env").write_text("API_TOKEN=should-not-escape\n", encoding="utf-8")
        subprocess.run(["git", "init"], cwd=target, check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=target, check=True, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture"],
            cwd=target,
            check=True,
            capture_output=True,
        )
        return temporary, command_directory, target

    @staticmethod
    def payload(observation_ref: str, **overrides: object) -> dict:
        value = {
            "schema_version": 1,
            "stage": "discovery",
            "evidence": [{"alias": "container", "observation_ref": observation_ref}],
            "claims": [{"id": "claim-container", "status": "confirmed", "evidence_aliases": ["container"]}],
            "rule_applications": [],
            "signals": ["container-runtime"],
            "candidate_ids": ["candidate-web"],
            "decisions": ["decision-runtime"],
        }
        value.update(overrides)
        return value

    def start_with_observation(self) -> tuple[tempfile.TemporaryDirectory[str], Server, Path, dict, dict]:
        temporary, command_directory, target = self.fixture()
        server = Server(command_directory=command_directory)
        started = server.tool_call("start_analysis", {"target_path": "external-target", "mode": "summary"})[0]
        observation, failed = server.tool_call("read_evidence", {"path": "Dockerfile"})
        self.assertFalse(failed, observation)
        return temporary, server, target, started, observation

    def test_submit_discovery_returns_redacted_processed_output_and_execution_handoff(self) -> None:
        temporary, server, _, started, observation = self.start_with_observation()
        with temporary:
            result, failed = server.tool_call(
                "submit_discovery",
                {"payload": self.payload(observation["observation_ref"])} ,
            )

        self.assertFalse(failed)
        self.assertEqual(result["completed_stage"], "discovery")
        self.assertEqual(result["next_skill"], "analyze-k8s-execution")
        self.assertEqual(result["accepted_output"], {
            "candidate_ids": ["candidate-web"],
            "discovery_fact_refs": ["fact_discovery_claim-container"],
            "unknown_ids": [],
        })
        stage_input = dict(result["stage_input"])
        survey = stage_input.pop("survey")
        budget = stage_input.pop("budget")
        self.assertEqual(stage_input, result["accepted_output"] | {"mode": "summary"})
        self.assertEqual(survey["stage"], "execution")
        self.assertTrue(survey["surveyed"])
        self.assertLessEqual(len(survey["observations"]), 12)
        self.assertEqual(budget, {"precision_calls_remaining": 1, "submit_rejections_remaining": 3})
        self.assertEqual(result["revision"], 1)
        self.assertNotEqual(result["transition_token"], started["transition_token"])
        rendered = json.dumps(result, sort_keys=True)
        self.assertNotIn("should-not-escape", rendered)
        handoff_only = json.dumps({**result, "stage_input": stage_input}, sort_keys=True)
        self.assertNotIn("Dockerfile", handoff_only)
        self.assertNotIn("observation_ref", handoff_only)
        # The pushed execution survey legitimately carries its own fresh
        # observation refs and safe path:line references for the next stage.
        self.assertIn("Dockerfile", json.dumps(survey, sort_keys=True))
        self.assertIn("observation_ref", json.dumps(survey, sort_keys=True))

    def test_rejects_forged_cross_stage_and_invalid_payloads_without_advancing(self) -> None:
        temporary, server, target, started, observation = self.start_with_observation()
        with temporary:
            forged, forged_failed = server.tool_call(
                "submit_discovery",
                {"payload": self.payload("obs_forged")},
            )
            cross_ref = server.session.registry.issue_present("execution", target / "Dockerfile", 1, 1, "1: FROM python:3.13")
            cross_stage, cross_stage_failed = server.tool_call(
                "submit_discovery",
                {"payload": self.payload(cross_ref["observation_ref"])},
            )
            invalid, invalid_failed = server.tool_call(
                "submit_discovery",
                {"payload": self.payload(observation["observation_ref"], signals=[])},
            )

        self.assertTrue(forged_failed)
        self.assertEqual(forged["code"], "unknown observation reference")
        self.assertTrue(cross_stage_failed)
        self.assertEqual(cross_stage["code"], "observation_stage_mismatch")
        self.assertTrue(cross_stage["retryable"])
        self.assertIn("current discovery stage", cross_stage["issues"][0])
        self.assertTrue(invalid_failed)
        self.assertEqual(server.session.current_stage, "discovery")
        self.assertEqual(server.session.revision, 0)
        self.assertEqual(server.session.transition_token, started["transition_token"])

    def test_rejects_a_repeat_discovery_submit_once_the_stage_has_advanced(self) -> None:
        # There is no client-supplied revision/token to go stale anymore; a
        # resubmission after a successful transition is now just an
        # out-of-order call against the new current stage.
        temporary, server, _, started, observation = self.start_with_observation()
        with temporary:
            accepted, failed = server.tool_call(
                "submit_discovery",
                {"payload": self.payload(observation["observation_ref"])},
            )
            repeated, repeated_failed = server.tool_call(
                "submit_discovery",
                {"payload": self.payload(observation["observation_ref"])},
            )

        self.assertFalse(failed)
        self.assertTrue(repeated_failed)
        self.assertEqual(repeated["code"], "stage_order")
        self.assertEqual(server.session.current_stage, "execution")
        self.assertEqual(server.session.revision, accepted["revision"])

    def test_rejects_ungrounded_and_malformed_claims_without_terminating_the_session(self) -> None:
        temporary, server, _, started, observation = self.start_with_observation()
        with temporary:
            missing_status, missing_status_failed = server.tool_call(
                "submit_discovery",
                {
                    "payload": self.payload(
                        observation["observation_ref"],
                        claims=[{"id": "claim-container", "evidence_aliases": ["container"]}],
                    ),
                },
            )
            ungrounded, ungrounded_failed = server.tool_call(
                "submit_discovery",
                {
                    "payload": self.payload(observation["observation_ref"], evidence=[], claims=[]),
                },
            )
            unsafe_id, unsafe_id_failed = server.tool_call(
                "submit_discovery",
                {
                    "payload": self.payload(
                        observation["observation_ref"],
                        claims=[{"id": "token=should-not-escape", "status": "confirmed", "evidence_aliases": ["container"]}],
                    ),
                },
            )

        self.assertTrue(missing_status_failed)
        self.assertTrue(ungrounded_failed)
        self.assertTrue(unsafe_id_failed)
        self.assertEqual(server.session.current_stage, "discovery")
        self.assertEqual(server.session.revision, 0)
        self.assertEqual(server.session.transition_token, started["transition_token"])
        self.assertNotIn("should-not-escape", json.dumps(unsafe_id, sort_keys=True))
