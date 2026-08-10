import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from analysis_pipeline.mcp_server import Server
from analysis_pipeline.stage_contracts import client_payload_required_fields, relationship_edge_contract


class RelationshipsStageTests(unittest.TestCase):
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
    def execution_payload(observation_ref: str, discovery_fact_refs: list[str]) -> dict:
        return {
            "schema_version": 1,
            "stage": "execution",
            "evidence": [{"alias": "runtime", "observation_ref": observation_ref}],
            "claims": [{"id": "claim-process", "status": "confirmed", "evidence_aliases": ["runtime"]}],
            "rule_applications": [],
            "discovery_fact_refs": discovery_fact_refs,
            "process_ids": ["process-web"],
        }

    @staticmethod
    def relationships_payload(
        observation_ref: str,
        discovery_fact_refs: list[str],
        execution_fact_refs: list[str],
        **overrides: object,
    ) -> dict:
        value = {
            "schema_version": 1,
            "stage": "relationships",
            "evidence": [{"alias": "dependency", "observation_ref": observation_ref}],
            "claims": [{"id": "claim-api-db", "status": "confirmed", "evidence_aliases": ["dependency"]}],
            "rule_applications": [],
            "discovery_fact_refs": discovery_fact_refs,
            "execution_fact_refs": execution_fact_refs,
            "graph_edges": [{
                "id": "edge-api-db",
                "source_process_id": "process-web",
                "target_id": "external-db",
                "target_kind": "external_system",
                "dependency_type": "data_store",
                "mechanism": "postgres",
                "endpoint_name": "database-url",
                "required_for_function": "confirmed",
                "startup_use": "unknown",
                "management_boundary": "externally_managed",
                "timing": "runtime",
                "execution_location": "server_process",
                "claim_ids": ["claim-api-db"],
                "status": "confirmed",
            }],
        }
        value.update(overrides)
        return value

    def start_with_execution(self, mode: str = "summary") -> tuple[tempfile.TemporaryDirectory[str], Server, Path, dict, dict]:
        temporary, command_directory, target = self.fixture()
        server = Server(command_directory=command_directory)
        started, failed = server.tool_call("start_analysis", {"target_path": "external-target", "mode": mode})
        self.assertFalse(failed, started)
        discovery_observation, failed = server.tool_call("read_evidence", {"path": "Dockerfile"})
        self.assertFalse(failed, discovery_observation)
        discovery, failed = server.tool_call(
            "submit_discovery",
            {"payload": self.discovery_payload(discovery_observation["observation_ref"])},
        )
        self.assertFalse(failed, discovery)
        execution_observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
        self.assertFalse(failed, execution_observation)
        execution, failed = server.tool_call(
            "submit_execution",
            {
                "payload": self.execution_payload(
                    execution_observation["observation_ref"], discovery["stage_input"]["discovery_fact_refs"]
                ),
            },
        )
        self.assertFalse(failed, execution)
        return temporary, server, target, discovery, execution

    def test_submit_relationships_returns_redacted_boundaries_handoff(self) -> None:
        temporary, server, _, discovery, execution = self.start_with_execution()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            result, failed = server.tool_call(
                "submit_relationships",
                {
                    "payload": self.relationships_payload(
                        observation["observation_ref"],
                        discovery["stage_input"]["discovery_fact_refs"],
                        execution["stage_input"]["execution_fact_refs"],
                    ),
                },
            )

        self.assertFalse(failed, result)
        self.assertEqual(result["completed_stage"], "relationships")
        self.assertEqual(result["next_skill"], "analyze-k8s-boundaries")
        self.assertEqual(result["accepted_output"], {
            "graph_edge_ids": ["edge-api-db"],
            "relationship_fact_refs": ["fact_relationships_claim-api-db"],
            "unknown_ids": [],
        })
        stage_input = dict(result["stage_input"])
        survey = stage_input.pop("survey")
        budget = stage_input.pop("budget")
        self.assertEqual(stage_input, result["accepted_output"] | {
            "mode": "summary",
            "discovery_fact_refs": ["fact_discovery_claim-container"],
            "execution_fact_refs": ["fact_execution_claim-process"],
            "candidate_ids": ["candidate-web"],
            "process_ids": ["process-web"],
        })
        self.assertEqual(survey["stage"], "boundaries")
        self.assertTrue(survey["surveyed"])
        self.assertLessEqual(len(survey["observations"]), 12)
        self.assertEqual(budget, {"precision_calls_remaining": 1, "submit_rejections_remaining": 3})
        handoff_only = json.dumps({**result, "stage_input": stage_input}, sort_keys=True)
        self.assertNotIn("app.py", handoff_only)
        self.assertNotIn("observation_ref", handoff_only)

    def test_rejects_foreign_fact_or_observation_without_advancing(self) -> None:
        temporary, server, target, discovery, execution = self.start_with_execution()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            foreign_fact, foreign_fact_failed = server.tool_call(
                "submit_relationships",
                {
                    "payload": self.relationships_payload(
                        observation["observation_ref"],
                        ["fact_discovery_foreign"],
                        execution["stage_input"]["execution_fact_refs"],
                    ),
                },
            )
            foreign_observation = server.session.registry.issue_present(
                "execution", target / "app.py", 1, 1, "1: print('ready')"
            )
            foreign_result, foreign_observation_failed = server.tool_call(
                "submit_relationships",
                {
                    "payload": self.relationships_payload(
                        foreign_observation["observation_ref"],
                        discovery["stage_input"]["discovery_fact_refs"],
                        execution["stage_input"]["execution_fact_refs"],
                    ),
                },
            )

        self.assertTrue(foreign_fact_failed)
        self.assertTrue(foreign_observation_failed)
        self.assertEqual(foreign_result["code"], "observation_stage_mismatch")
        self.assertTrue(foreign_result["retryable"])
        self.assertIn("current relationships stage", foreign_result["issues"][0])
        self.assertEqual(server.session.current_stage, "relationships")
        self.assertEqual(server.session.revision, execution["revision"])
        self.assertEqual(server.session.transition_token, execution["transition_token"])
        self.assertNotIn("foreign", json.dumps(foreign_fact, sort_keys=True))
        self.assertNotIn("app.py", json.dumps(foreign_result, sort_keys=True))

    def test_unknown_relationship_edge_field_is_retryable_with_the_public_contract(self) -> None:
        temporary, server, _, discovery, execution = self.start_with_execution()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            payload = self.relationships_payload(
                observation["observation_ref"],
                discovery["stage_input"]["discovery_fact_refs"],
                execution["stage_input"]["execution_fact_refs"],
            )
            payload["graph_edges"][0]["invented_field"] = "nope"
            result, failed = server.tool_call("submit_relationships", {"payload": payload})

        self.assertTrue(failed)
        self.assertEqual(result["code"], "invalid_nested_stage_payload")
        self.assertTrue(result["retryable"])
        self.assertIn("payload.graph_edges[] permits only", result["issues"][0])

    def test_relationships_accepts_scoped_unknown_with_absence_evidence(self) -> None:
        temporary, server, _, discovery, execution = self.start_with_execution("detailed")
        with temporary:
            absence = server.session.registry.issue_absence("relationships", ".", "*.yaml", "DATABASE_URL")
            result, failed = server.tool_call(
                "submit_relationships",
                {
                    "payload": self.relationships_payload(
                        absence["observation_ref"],
                        discovery["stage_input"]["discovery_fact_refs"],
                        execution["stage_input"]["execution_fact_refs"],
                        claims=[{
                            "id": "claim-db-endpoint",
                            "status": "unknown",
                            "evidence_aliases": ["dependency"],
                            "scope": "runtime database endpoint",
                            "blocked_decision": "database service binding",
                        }],
                        graph_edges=[],
                    ),
                },
            )

        self.assertFalse(failed, result)
        self.assertEqual(result["mode"], "detailed")
        self.assertEqual(result["accepted_output"]["unknown_ids"], ["claim-db-endpoint"])

    def test_relationships_rejects_a_confirmed_claim_without_an_edge(self) -> None:
        temporary, server, _, discovery, execution = self.start_with_execution()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            result, rejected = server.tool_call(
                "submit_relationships",
                {
                    "payload": self.relationships_payload(
                        observation["observation_ref"],
                        discovery["stage_input"]["discovery_fact_refs"],
                        execution["stage_input"]["execution_fact_refs"],
                        graph_edges=[],
                    ),
                },
            )

        self.assertTrue(rejected)
        self.assertEqual(server.session.current_stage, "relationships")
        self.assertNotIn("claim-api-db", json.dumps(result, sort_keys=True))

    def test_relationships_accepts_marked_conflicts_linked_to_conflicted_claims(self) -> None:
        temporary, server, _, discovery, execution = self.start_with_execution()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            base = self.relationships_payload(
                observation["observation_ref"],
                discovery["stage_input"]["discovery_fact_refs"],
                execution["stage_input"]["execution_fact_refs"],
            )["graph_edges"][0]
            conflict = {**base, "id": "edge-api-db-conflict", "mechanism": "mysql", "status": "conflicted"}
            result, failed = server.tool_call(
                "submit_relationships",
                {
                    "payload": self.relationships_payload(
                        observation["observation_ref"],
                        discovery["stage_input"]["discovery_fact_refs"],
                        execution["stage_input"]["execution_fact_refs"],
                        claims=[{"id": "claim-api-db", "status": "conflicted", "evidence_aliases": ["dependency"]}],
                        graph_edges=[{**base, "status": "conflicted"}, conflict],
                    ),
                },
            )

        self.assertFalse(failed, result)
        self.assertEqual(result["accepted_output"]["relationship_fact_refs"], ["fact_relationships_claim-api-db"])

    def test_relationships_required_fields_are_loaded_from_the_stage_contract(self) -> None:
        self.assertEqual(
            client_payload_required_fields("relationships"),
            {
                "schema_version", "stage", "evidence", "claims", "rule_applications",
                "discovery_fact_refs", "execution_fact_refs", "graph_edges",
            },
        )

    def test_relationship_edge_schema_is_loaded_from_the_stage_contract(self) -> None:
        source = json.loads((Path(__file__).resolve().parents[3] / "contracts/stage-payload-contracts.json").read_text(encoding="utf-8"))
        self.assertEqual(
            relationship_edge_contract(),
            source["stages"]["relationships"]["client_payload"]["graph_edges"],
        )

    def test_rejects_a_relationship_edge_with_a_dangling_process_or_claim(self) -> None:
        temporary, server, _, discovery, execution = self.start_with_execution()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            dangling_edge = self.relationships_payload(
                observation["observation_ref"],
                discovery["stage_input"]["discovery_fact_refs"],
                execution["stage_input"]["execution_fact_refs"],
                graph_edges=[{
                    "id": "edge-dangling",
                    "source_process_id": "process-missing",
                    "target_id": "external-db",
                    "target_kind": "external_system",
                    "dependency_type": "data_store",
                    "mechanism": "postgres",
                    "endpoint_name": "database-url",
                    "required_for_function": "confirmed",
                    "startup_use": "unknown",
                    "management_boundary": "externally_managed",
                    "timing": "runtime",
                    "execution_location": "server_process",
                    "claim_ids": ["claim-missing"],
                    "status": "confirmed",
                }],
            )
            result, rejected = server.tool_call(
                "submit_relationships", {"payload": dangling_edge}
            )

        self.assertTrue(rejected)
        self.assertEqual(server.session.current_stage, "relationships")
        self.assertEqual(server.session.revision, execution["revision"])
        self.assertNotIn("process-missing", json.dumps(result, sort_keys=True))

    def test_relationships_preserves_a_process_cycle_and_requires_conflict_status(self) -> None:
        temporary, server, _, discovery, execution = self.start_with_execution()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            cycle = self.relationships_payload(
                observation["observation_ref"],
                discovery["stage_input"]["discovery_fact_refs"],
                execution["stage_input"]["execution_fact_refs"],
                graph_edges=[{
                    "id": "edge-self-cycle",
                    "source_process_id": "process-web",
                    "target_id": "process-web",
                    "target_kind": "process",
                    "dependency_type": "service",
                    "mechanism": "http",
                    "endpoint_name": "self-api",
                    "required_for_function": "confirmed",
                    "startup_use": "confirmed",
                    "management_boundary": "repository_managed",
                    "timing": "runtime",
                    "execution_location": "server_process",
                    "claim_ids": ["claim-api-db"],
                    "status": "confirmed",
                }],
            )
            accepted, accepted_failed = server.tool_call(
                "submit_relationships", {"payload": cycle}
            )

        self.assertFalse(accepted_failed, accepted)
        self.assertEqual(accepted["accepted_output"]["graph_edge_ids"], ["edge-self-cycle"])

    def test_rejects_unmarked_conflicting_relationship_edges(self) -> None:
        temporary, server, _, discovery, execution = self.start_with_execution()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            base = self.relationships_payload(
                observation["observation_ref"],
                discovery["stage_input"]["discovery_fact_refs"],
                execution["stage_input"]["execution_fact_refs"],
            )["graph_edges"][0]
            conflict = {**base, "id": "edge-api-db-conflict", "mechanism": "mysql"}
            result, rejected = server.tool_call(
                "submit_relationships",
                {
                    "payload": self.relationships_payload(
                        observation["observation_ref"],
                        discovery["stage_input"]["discovery_fact_refs"],
                        execution["stage_input"]["execution_fact_refs"],
                        graph_edges=[base, conflict],
                    ),
                },
            )

        self.assertTrue(rejected)
        self.assertEqual(server.session.current_stage, "relationships")
        self.assertNotIn("mysql", json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
