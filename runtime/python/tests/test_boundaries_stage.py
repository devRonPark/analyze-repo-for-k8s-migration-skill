import json
import os
import unittest
from pathlib import Path

from analysis_pipeline.mcp_server import Server
from analysis_pipeline.stage_contracts import client_payload_required_fields
from analysis_pipeline.transitions import reopen
from runtime.python.tests.test_relationships_stage import RelationshipsStageTests


class BoundariesStageTests(unittest.TestCase):
    @staticmethod
    def payload(observation_ref: str, handoff: dict, **overrides: object) -> dict:
        value = {
            "schema_version": 1,
            "stage": "boundaries",
            "evidence": [{"alias": "boundary", "observation_ref": observation_ref}],
            "claims": [
                {"id": "claim-web-boundary", "status": "confirmed", "evidence_aliases": ["boundary"]},
                {"id": "claim-web-lifecycle", "status": "confirmed", "evidence_aliases": ["boundary"]},
                {"id": "claim-web-state", "status": "confirmed", "evidence_aliases": ["boundary"]},
                {"id": "claim-web-deployability", "status": "confirmed", "evidence_aliases": ["boundary"]},
            ],
            "rule_applications": [],
            "discovery_fact_refs": handoff["stage_input"]["discovery_fact_refs"],
            "execution_fact_refs": handoff["stage_input"]["execution_fact_refs"],
            "relationship_fact_refs": handoff["stage_input"]["relationship_fact_refs"],
            "workload_units": [{
                "id": "unit-web",
                "process_ids": ["process-web"],
                "candidate_ids": ["candidate-web"],
                "start_definition_status": "confirmed",
                "independent_lifecycle_status": "confirmed",
                "boundary_status": "confirmed",
                "lifecycle": "continuous",
                "state_decision": "externalized",
                "deployable": True,
                "deployability_status": "confirmed",
                "boundary_claim_ids": ["claim-web-boundary"],
                "lifecycle_claim_ids": ["claim-web-lifecycle"],
                "state_claim_ids": ["claim-web-state"],
                "deployability_claim_ids": ["claim-web-deployability"],
            }],
            "candidate_exclusions": [],
        }
        value.update(overrides)
        return value

    def start_with_relationships(self) -> tuple[object, object, Path, dict]:
        helper = RelationshipsStageTests()
        temporary, server, target, discovery, execution = helper.start_with_execution()
        observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
        self.assertFalse(failed, observation)
        relationships, failed = server.tool_call(
            "submit_relationships",
            {
                "payload": helper.relationships_payload(
                    observation["observation_ref"],
                    discovery["stage_input"]["discovery_fact_refs"],
                    execution["stage_input"]["execution_fact_refs"],
                ),
            },
        )
        self.assertFalse(failed, relationships)
        return temporary, server, target, relationships

    def test_submit_boundaries_returns_redacted_contracts_handoff(self) -> None:
        temporary, server, _, relationships = self.start_with_relationships()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            result, failed = server.tool_call(
                "submit_boundaries", {"payload": self.payload(observation["observation_ref"], relationships)}
            )

        self.assertFalse(failed, result)
        self.assertEqual(result["next_skill"], "analyze-k8s-contracts")
        self.assertEqual(result["accepted_output"], {
            "unit_ids": ["unit-web"], "deployable_unit_ids": ["unit-web"],
            "included_candidate_ids": ["candidate-web"], "excluded_candidate_ids": [],
            "boundaries_fact_refs": [
                "fact_boundaries_claim-web-boundary",
                "fact_boundaries_claim-web-lifecycle",
                "fact_boundaries_claim-web-state",
                "fact_boundaries_claim-web-deployability",
            ], "unknown_ids": [],
        })
        self.assertNotIn("app.py", json.dumps(result, sort_keys=True))

    def test_rejects_duplicate_or_dangling_boundary_units_without_advancing(self) -> None:
        temporary, server, _, relationships = self.start_with_relationships()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            unit = self.payload(observation["observation_ref"], relationships)["workload_units"][0]
            result, rejected = server.tool_call(
                "submit_boundaries",
                {"payload": self.payload(
                    observation["observation_ref"], relationships,
                    workload_units=[unit, {**unit, "id": "unit-other", "process_ids": ["process-missing"]}],
                )},
            )

        self.assertTrue(rejected)
        self.assertEqual(server.session.current_stage, "boundaries")
        self.assertEqual(server.session.revision, relationships["revision"])
        self.assertNotIn("process-missing", json.dumps(result, sort_keys=True))

    def test_rejects_deployable_unit_without_both_boundary_conditions(self) -> None:
        temporary, server, _, relationships = self.start_with_relationships()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            unit = self.payload(observation["observation_ref"], relationships)["workload_units"][0]
            result, rejected = server.tool_call(
                "submit_boundaries",
                {"payload": self.payload(
                    observation["observation_ref"], relationships,
                    workload_units=[{**unit, "independent_lifecycle_status": "unknown", "boundary_status": "unknown"}],
                )},
            )

        self.assertTrue(rejected)
        self.assertEqual(server.session.current_stage, "boundaries")
        self.assertNotIn("unit-web", json.dumps(result, sort_keys=True))

    def test_rejects_unlinked_or_status_mismatched_boundary_claim(self) -> None:
        temporary, server, _, relationships = self.start_with_relationships()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            result, rejected = server.tool_call(
                "submit_boundaries",
                {"payload": self.payload(
                    observation["observation_ref"], relationships,
                    claims=[
                        {"id": "claim-web-boundary", "status": "inferred", "evidence_aliases": ["boundary"]},
                        {"id": "claim-web-lifecycle", "status": "confirmed", "evidence_aliases": ["boundary"]},
                        {"id": "claim-web-state", "status": "confirmed", "evidence_aliases": ["boundary"]},
                        {"id": "claim-web-deployability", "status": "confirmed", "evidence_aliases": ["boundary"]},
                    ],
                )},
            )

        self.assertTrue(rejected)
        self.assertEqual(server.session.current_stage, "boundaries")

    def test_rejects_confirmed_boundary_with_unknown_conditions(self) -> None:
        temporary, server, _, relationships = self.start_with_relationships()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            unit = self.payload(observation["observation_ref"], relationships)["workload_units"][0]
            result, rejected = server.tool_call("submit_boundaries", {"payload": self.payload(observation["observation_ref"], relationships, workload_units=[{**unit, "start_definition_status": "unknown", "independent_lifecycle_status": "unknown", "deployable": False}] )})
        self.assertTrue(rejected)
        self.assertNotIn("unit-web", json.dumps(result, sort_keys=True))

    def test_boundaries_required_fields_are_loaded_from_stage_contract(self) -> None:
        self.assertIn("workload_units", client_payload_required_fields("boundaries"))

    def test_accepts_deployable_single_process_unit_with_unknown_independent_lifecycle(self) -> None:
        """A single accepted runtime process has no sibling to compare an
        independent lifecycle against, so Workload Grouping is deterministic
        and independent_lifecycle_status is not required to be confirmed."""
        temporary, server, _, relationships = self.start_with_relationships()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            unit = self.payload(observation["observation_ref"], relationships)["workload_units"][0]
            result, rejected = server.tool_call(
                "submit_boundaries",
                {"payload": self.payload(
                    observation["observation_ref"], relationships,
                    workload_units=[{**unit, "independent_lifecycle_status": "unknown"}],
                )},
            )

        self.assertFalse(rejected, result)
        self.assertEqual(result["accepted_output"]["unit_ids"], ["unit-web"])
        self.assertEqual(result["accepted_output"]["deployable_unit_ids"], ["unit-web"])

    def start_with_two_process_relationships(self) -> tuple[object, object, Path, dict]:
        """A two-process Execution handoff, unlike `start_with_relationships`'
        single `process-web`: exercises the case where Workload Grouping is
        not deterministic and comparative lifecycle evidence still applies."""
        helper = RelationshipsStageTests()
        temporary, command_directory, target = helper.fixture()
        server = Server(command_directory=command_directory)
        started, failed = server.tool_call("start_analysis", {"target_path": "external-target", "mode": "summary"})
        self.assertFalse(failed, started)
        discovery_observation, failed = server.tool_call("read_evidence", {"path": "Dockerfile"})
        self.assertFalse(failed, discovery_observation)
        discovery, failed = server.tool_call(
            "submit_discovery", {"payload": helper.discovery_payload(discovery_observation["observation_ref"])}
        )
        self.assertFalse(failed, discovery)
        execution_observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
        self.assertFalse(failed, execution_observation)
        execution, failed = server.tool_call(
            "submit_execution",
            {
                "payload": helper.execution_payload(
                    execution_observation["observation_ref"],
                    discovery["stage_input"]["discovery_fact_refs"],
                    process_ids=["process-web", "process-worker"],
                ),
            },
        )
        self.assertFalse(failed, execution)
        observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
        self.assertFalse(failed, observation)
        relationships, failed = server.tool_call(
            "submit_relationships",
            {
                "payload": helper.relationships_payload(
                    observation["observation_ref"],
                    discovery["stage_input"]["discovery_fact_refs"],
                    execution["stage_input"]["execution_fact_refs"],
                ),
            },
        )
        self.assertFalse(failed, relationships)
        return temporary, server, target, relationships

    def test_rejects_deployable_multi_process_group_with_unknown_independent_lifecycle(self) -> None:
        """Unlike a single process, a multi-process group merges evidence
        about more than one process, so the independent-lifecycle coupling
        must still hold -- Workload Grouping is not deterministic there."""
        temporary, server, _, relationships = self.start_with_two_process_relationships()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            unit = self.payload(observation["observation_ref"], relationships)["workload_units"][0]
            result, rejected = server.tool_call(
                "submit_boundaries",
                {"payload": self.payload(
                    observation["observation_ref"], relationships,
                    workload_units=[{
                        **unit,
                        "process_ids": ["process-web", "process-worker"],
                        "independent_lifecycle_status": "unknown",
                    }],
                )},
            )

        self.assertTrue(rejected)
        self.assertEqual(server.session.current_stage, "boundaries")

    def test_accepts_confirmed_boundary_with_independently_unknown_state(self) -> None:
        temporary, server, _, relationships = self.start_with_relationships()
        with temporary:
            present, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, present)
            absence = server.session.registry.issue_absence("boundaries", ".", "*.yaml", "STATE_PATH")
            payload = self.payload(
                present["observation_ref"],
                relationships,
                evidence=[
                    {"alias": "boundary", "observation_ref": present["observation_ref"]},
                    {"alias": "state", "observation_ref": absence["observation_ref"]},
                ],
                claims=[
                    {"id": "claim-web-boundary", "status": "confirmed", "evidence_aliases": ["boundary"]},
                    {"id": "claim-web-lifecycle", "status": "confirmed", "evidence_aliases": ["boundary"]},
                    {
                        "id": "claim-web-state", "status": "unknown", "evidence_aliases": ["state"],
                        "scope": "web writable-state configuration", "blocked_decision": "web state backing service",
                    },
                    {"id": "claim-web-deployability", "status": "confirmed", "evidence_aliases": ["boundary"]},
                ],
                workload_units=[{
                    **self.payload(present["observation_ref"], relationships)["workload_units"][0],
                    "state_decision": "unknown",
                }],
            )
            result, rejected = server.tool_call("submit_boundaries", {"payload": payload})

        self.assertFalse(rejected, result)
        self.assertEqual(result["accepted_output"]["unknown_ids"], ["claim-web-state"])
        self.assertIn("fact_boundaries_claim-web-boundary", result["accepted_output"]["boundaries_fact_refs"])

    def test_requires_every_candidate_to_be_included_or_claimed_as_excluded(self) -> None:
        temporary, server, _, relationships = self.start_with_relationships()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            unit = self.payload(observation["observation_ref"], relationships)["workload_units"][0]
            omitted, rejected = server.tool_call(
                "submit_boundaries",
                {
                    "payload": self.payload(
                        observation["observation_ref"], relationships,
                        workload_units=[{**unit, "candidate_ids": [], "deployable": False}],
                    ),
                },
            )
            self.assertTrue(rejected)
            self.assertEqual(server.session.current_stage, "boundaries")
            accepted, failed = server.tool_call(
                "submit_boundaries",
                {
                    "payload": self.payload(
                        observation["observation_ref"], relationships,
                        claims=[
                            {"id": "claim-web-boundary", "status": "confirmed", "evidence_aliases": ["boundary"]},
                            {"id": "claim-web-lifecycle", "status": "confirmed", "evidence_aliases": ["boundary"]},
                            {"id": "claim-web-state", "status": "confirmed", "evidence_aliases": ["boundary"]},
                            {"id": "claim-web-deployability", "status": "confirmed", "evidence_aliases": ["boundary"]},
                            {"id": "claim-web-candidate-exclusion", "status": "confirmed", "evidence_aliases": ["boundary"]},
                        ],
                        workload_units=[{**unit, "candidate_ids": [], "deployable": False}],
                        candidate_exclusions=[{
                            "candidate_id": "candidate-web", "disposition": "excluded",
                            "claim_ids": ["claim-web-candidate-exclusion"],
                        }],
                    ),
                },
            )

        self.assertFalse(failed, accepted)
        self.assertNotIn("candidate-web", accepted["accepted_output"]["included_candidate_ids"])
        self.assertEqual(accepted["accepted_output"]["excluded_candidate_ids"], ["candidate-web"])
        self.assertNotIn("candidate-web", json.dumps(omitted, sort_keys=True))

    def test_reopen_from_contracts_to_boundaries_discards_only_boundary_facts_and_units(self) -> None:
        temporary, server, _, relationships = self.start_with_relationships()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            contracts, failed = server.tool_call(
                "submit_boundaries",
                {"payload": self.payload(observation["observation_ref"], relationships)},
            )
            self.assertFalse(failed, contracts)

        reopened = reopen(
            server.session.pipeline,
            "boundaries",
            "boundary state needs correction",
            server.session.pipeline.revision,
            server.session.pipeline.state_hash,
        )

        self.assertEqual(reopened.current_stage, "boundaries")
        self.assertIn("relationships", reopened.outputs)
        self.assertNotIn("boundaries", reopened.outputs)
        self.assertNotIn("unit-web", reopened.catalog["unit_ids"])
        self.assertFalse(any(item["stage"] == "boundaries" for item in reopened.evidence.values()))

    def test_summary_and_detailed_boundary_handoffs_preserve_the_requested_mode(self) -> None:
        for mode in ("summary", "detailed"):
            with self.subTest(mode=mode):
                helper = RelationshipsStageTests()
                temporary, server, _, discovery, execution = helper.start_with_execution(mode)
                with temporary:
                    observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
                    self.assertFalse(failed, observation)
                    relationships, failed = server.tool_call(
                        "submit_relationships",
                        {
                            "payload": helper.relationships_payload(
                                observation["observation_ref"],
                                discovery["stage_input"]["discovery_fact_refs"],
                                execution["stage_input"]["execution_fact_refs"],
                            ),
                        },
                    )
                    self.assertFalse(failed, relationships)
                    observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
                    self.assertFalse(failed, observation)
                    result, failed = server.tool_call(
                        "submit_boundaries",
                        {"payload": self.payload(observation["observation_ref"], relationships)},
                    )

                self.assertFalse(failed, result)
                self.assertEqual(result["mode"], mode)
                self.assertEqual(result["stage_input"]["mode"], mode)

    def test_multiple_empty_claim_link_fields_are_reported_together(self) -> None:
        temporary, server, _, relationships = self.start_with_relationships()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            unit = self.payload(observation["observation_ref"], relationships)["workload_units"][0]
            result, rejected = server.tool_call(
                "submit_boundaries",
                {"payload": self.payload(
                    observation["observation_ref"], relationships,
                    workload_units=[{
                        **unit,
                        "boundary_status": "unknown", "boundary_claim_ids": [],
                        "lifecycle": "unknown", "lifecycle_claim_ids": [],
                        "state_decision": "unknown", "state_claim_ids": [],
                        "deployable": False,
                    }],
                )},
            )

        self.assertTrue(rejected)
        message = result["issues"][0]
        self.assertIn("unit-web", message)
        self.assertIn("boundary_claim_ids", message)
        self.assertIn("lifecycle_claim_ids", message)
        self.assertIn("state_claim_ids", message)

    def test_empty_unknown_lifecycle_claim_ids_names_the_field_and_reason(self) -> None:
        temporary, server, _, relationships = self.start_with_relationships()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            unit = self.payload(observation["observation_ref"], relationships)["workload_units"][0]
            result, rejected = server.tool_call(
                "submit_boundaries",
                {"payload": self.payload(
                    observation["observation_ref"], relationships,
                    workload_units=[{**unit, "lifecycle": "unknown", "lifecycle_claim_ids": []}],
                )},
            )

        self.assertTrue(rejected)
        message = result["issues"][0]
        self.assertIn("unit-web", message)
        self.assertIn("lifecycle_claim_ids", message)
        self.assertIn("unknown", message)
        self.assertNotEqual(message, "workload claim dangling")

    def test_claim_status_mismatch_names_expected_and_actual_status(self) -> None:
        temporary, server, _, relationships = self.start_with_relationships()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            unit = self.payload(observation["observation_ref"], relationships)["workload_units"][0]
            result, rejected = server.tool_call(
                "submit_boundaries",
                {"payload": self.payload(
                    observation["observation_ref"], relationships,
                    workload_units=[{**unit, "lifecycle": "unknown"}],
                )},
            )

        self.assertTrue(rejected)
        message = result["issues"][0]
        self.assertIn("lifecycle_claim_ids", message)
        self.assertIn("'unknown'", message)
        self.assertIn("claim-web-lifecycle", message)
        self.assertIn("'confirmed'", message)

    def test_missing_referenced_claim_id_is_distinct_from_empty_claim_array(self) -> None:
        temporary, server, _, relationships = self.start_with_relationships()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            unit = self.payload(observation["observation_ref"], relationships)["workload_units"][0]
            result, rejected = server.tool_call(
                "submit_boundaries",
                {"payload": self.payload(
                    observation["observation_ref"], relationships,
                    workload_units=[{**unit, "state_claim_ids": ["claim-state-missing"]}],
                )},
            )

        self.assertTrue(rejected)
        message = result["issues"][0]
        self.assertIn("state_claim_ids", message)
        self.assertIn("claim-state-missing", message)
        self.assertNotIn("at least one claim is required", message)

    def test_unlinked_boundary_claim_names_the_specific_claim_id(self) -> None:
        temporary, server, _, relationships = self.start_with_relationships()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            result, rejected = server.tool_call(
                "submit_boundaries",
                {"payload": self.payload(
                    observation["observation_ref"], relationships,
                    claims=[
                        {"id": "claim-web-boundary", "status": "confirmed", "evidence_aliases": ["boundary"]},
                        {"id": "claim-web-lifecycle", "status": "confirmed", "evidence_aliases": ["boundary"]},
                        {"id": "claim-web-state", "status": "confirmed", "evidence_aliases": ["boundary"]},
                        {"id": "claim-web-deployability", "status": "confirmed", "evidence_aliases": ["boundary"]},
                        {"id": "claim-web-orphan", "status": "confirmed", "evidence_aliases": ["boundary"]},
                    ],
                )},
            )

        self.assertTrue(rejected)
        message = result["issues"][0]
        self.assertIn("claim-web-orphan", message)
        self.assertNotEqual(message, "boundary claim requires workload unit")


if __name__ == "__main__":
    unittest.main()
