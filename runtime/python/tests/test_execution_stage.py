import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from analysis_pipeline.mcp_server import Server
from analysis_pipeline.stage_contracts import client_payload_required_fields


class ExecutionStageTests(unittest.TestCase):
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
    def execution_payload(observation_ref: str, discovery_fact_refs: list[str], **overrides: object) -> dict:
        value = {
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
        value.update(overrides)
        return value

    def start_with_discovery(self, mode: str = "summary") -> tuple[tempfile.TemporaryDirectory[str], Server, Path, dict, dict]:
        temporary, command_directory, target = self.fixture()
        server = Server(command_directory=command_directory)
        started, started_failed = server.tool_call("start_analysis", {"target_path": "external-target", "mode": mode})
        self.assertFalse(started_failed, started)
        discovery_observation, observation_failed = server.tool_call("read_evidence", {"path": "Dockerfile"})
        self.assertFalse(observation_failed, discovery_observation)
        discovery, discovery_failed = server.tool_call(
            "submit_discovery",
            {"payload": self.discovery_payload(discovery_observation["observation_ref"])},
        )
        self.assertFalse(discovery_failed, discovery)
        return temporary, server, target, started, discovery

    def test_submit_execution_returns_redacted_relationships_handoff(self) -> None:
        temporary, server, _, _, discovery = self.start_with_discovery()
        with temporary:
            observation, observation_failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(observation_failed, observation)
            result, failed = server.tool_call(
                "submit_execution",
                {
                    "payload": self.execution_payload(
                        observation["observation_ref"],
                        discovery["stage_input"]["discovery_fact_refs"],
                    ),
                },
            )
            # There is no client-supplied revision/token to go stale anymore;
            # a resubmission after a successful transition is now just an
            # out-of-order call against the new current stage.
            repeated, repeated_failed = server.tool_call(
                "submit_execution",
                {
                    "payload": self.execution_payload(
                        observation["observation_ref"],
                        discovery["stage_input"]["discovery_fact_refs"],
                    ),
                },
            )

        self.assertFalse(failed, result)
        self.assertEqual(result["completed_stage"], "execution")
        self.assertEqual(result["next_skill"], "analyze-k8s-relationships")
        process_ids = result["accepted_output"]["process_ids"]
        self.assertEqual(len(process_ids), 1)
        self.assertEqual(result["accepted_output"], {
            "runtime_processes": [{
                "id": process_ids[0],
                "candidate_ids": ["candidate-web"],
                "role": "unknown",
                "execution_pattern": "unknown",
                "semantic_fact_refs": [],
            }],
            "process_ids": process_ids,
            "execution_fact_refs": ["fact_execution_claim-process"],
            "unknown_ids": [],
        })
        stage_input = dict(result["stage_input"])
        survey = stage_input.pop("survey")
        budget = stage_input.pop("budget")
        self.assertEqual(stage_input, result["accepted_output"] | {
            "mode": "summary",
            "discovery_fact_refs": ["fact_discovery_claim-container"],
        })
        self.assertEqual(survey["stage"], "relationships")
        self.assertTrue(survey["surveyed"])
        self.assertLessEqual(len(survey["observations"]), 12)
        self.assertEqual(budget, {"precision_calls_remaining": 1, "submit_rejections_remaining": 3})
        self.assertEqual(result["revision"], discovery["revision"] + 1)
        self.assertNotEqual(result["transition_token"], discovery["transition_token"])
        self.assertTrue(repeated_failed)
        self.assertEqual(repeated["code"], "stage_order")
        handoff_only = json.dumps({**result, "stage_input": stage_input}, sort_keys=True)
        self.assertNotIn("Dockerfile", handoff_only)
        self.assertNotIn("observation_ref", handoff_only)

    def test_rejects_execution_before_discovery(self) -> None:
        temporary, command_directory, _ = self.fixture()
        with temporary:
            server = Server(command_directory=command_directory)
            started, started_failed = server.tool_call("start_analysis", {"target_path": "external-target", "mode": "summary"})
            self.assertFalse(started_failed, started)
            wrong_stage, wrong_stage_failed = server.tool_call(
                "submit_execution",
                {"payload": {}},
            )

        self.assertTrue(wrong_stage_failed)
        self.assertEqual(wrong_stage["code"], "stage_order")
        self.assertEqual(server.session.current_stage, "discovery")
        self.assertEqual(server.session.revision, started["revision"])

    def test_rejects_foreign_fact_and_foreign_observation_without_advancing(self) -> None:
        temporary, server, target, _, discovery = self.start_with_discovery()
        with temporary:
            execution_observation, observation_failed = server.tool_call("read_evidence", {"path": "Dockerfile"})
            self.assertFalse(observation_failed, execution_observation)
            foreign_fact, foreign_fact_failed = server.tool_call(
                "submit_execution",
                {
                    "payload": self.execution_payload(execution_observation["observation_ref"], ["fact_discovery-foreign"]),
                },
            )
            foreign_observation = server.session.registry.issue_present("discovery", target / "Dockerfile", 1, 1, "1: FROM python:3.13")
            foreign_observation_result, foreign_observation_failed = server.tool_call(
                "submit_execution",
                {
                    "payload": self.execution_payload(
                        foreign_observation["observation_ref"],
                        discovery["stage_input"]["discovery_fact_refs"],
                    ),
                },
            )

        self.assertTrue(foreign_fact_failed)
        self.assertTrue(foreign_observation_failed)
        self.assertEqual(server.session.current_stage, "execution")
        self.assertEqual(server.session.revision, discovery["revision"])
        self.assertEqual(server.session.transition_token, discovery["transition_token"])
        self.assertNotIn("Dockerfile", json.dumps(foreign_observation_result, sort_keys=True))
        self.assertNotIn("foreign", json.dumps(foreign_fact, sort_keys=True))

    def test_detailed_execution_preserves_the_mode_in_the_current_handoff(self) -> None:
        temporary, server, _, _, discovery = self.start_with_discovery("detailed")
        with temporary:
            observation, observation_failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(observation_failed, observation)
            result, failed = server.tool_call(
                "submit_execution",
                {
                    "payload": self.execution_payload(
                        observation["observation_ref"],
                        discovery["stage_input"]["discovery_fact_refs"],
                    ),
                },
            )

        self.assertFalse(failed, result)
        self.assertEqual(result["mode"], "detailed")
        self.assertEqual(result["stage_input"]["mode"], "detailed")

    def test_execution_rule_application_names_the_dangling_decision_id(self) -> None:
        temporary, server, _, _, discovery = self.start_with_discovery()
        with temporary:
            observation, observation_failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(observation_failed, observation)
            result, failed = server.tool_call(
                "submit_execution",
                {
                    "payload": self.execution_payload(
                        observation["observation_ref"],
                        discovery["stage_input"]["discovery_fact_refs"],
                        rule_applications=[
                            {
                                "rule_id": "rule-exec-decision",
                                "evidence_aliases": ["runtime"],
                                "process_or_candidate_ids": ["candidate-web"],
                                "decision_id": "claim_build_command",
                            }
                        ],
                    ),
                },
            )

        self.assertTrue(failed)
        message = result["issues"][0]
        # The invented decision_id, the offending rule, and the set of decision
        # ids actually declared so far (by discovery) must all be nameable --
        # a live model invents a decision_id describing its own stage's
        # concerns instead of reusing one an earlier stage declared, and the
        # old bare "rule decision dangling" gave it nothing to diagnose that with.
        self.assertIn("claim_build_command", message)
        self.assertIn("rule-exec-decision", message)
        self.assertIn("decision-runtime", message)
        self.assertNotEqual(message, "rule decision dangling")

    def test_execution_rule_application_names_the_dangling_subject_id(self) -> None:
        temporary, server, _, _, discovery = self.start_with_discovery()
        with temporary:
            observation, observation_failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(observation_failed, observation)
            result, failed = server.tool_call(
                "submit_execution",
                {
                    "payload": self.execution_payload(
                        observation["observation_ref"],
                        discovery["stage_input"]["discovery_fact_refs"],
                        rule_applications=[
                            {
                                "rule_id": "rule-exec-subject",
                                "evidence_aliases": ["runtime"],
                                "process_or_candidate_ids": ["process-ghost"],
                                "decision_id": "decision-runtime",
                            }
                        ],
                    ),
                },
            )

        self.assertTrue(failed)
        message = result["issues"][0]
        self.assertIn("process-ghost", message)
        self.assertIn("rule-exec-subject", message)
        self.assertNotEqual(message, "rule subject dangling")

    def test_execution_accepts_rule_application_referencing_a_declared_decision_and_subject(self) -> None:
        temporary, server, _, _, discovery = self.start_with_discovery()
        with temporary:
            observation, observation_failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(observation_failed, observation)
            result, failed = server.tool_call(
                "submit_execution",
                {
                    "payload": self.execution_payload(
                        observation["observation_ref"],
                        discovery["stage_input"]["discovery_fact_refs"],
                        rule_applications=[
                            {
                                "rule_id": "rule-exec-valid",
                                "evidence_aliases": ["runtime"],
                                "process_or_candidate_ids": ["candidate-web"],
                                "decision_id": "decision-runtime",
                            }
                        ],
                    ),
                },
            )

        self.assertFalse(failed, result)
        self.assertEqual(result["completed_stage"], "execution")

    def test_execution_required_fields_are_loaded_from_the_stage_contract(self) -> None:
        self.assertEqual(
            client_payload_required_fields("execution"),
            {
                "schema_version", "stage", "evidence", "claims", "rule_applications",
                "discovery_fact_refs", "runtime_processes",
            },
        )
