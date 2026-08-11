import json
import unittest

from analysis_pipeline.stage_contracts import assign_report_slot_facts

from runtime.python.tests.test_boundaries_stage import BoundariesStageTests
from runtime.python.tests.test_relationships_stage import RelationshipsStageTests


REPORT_SLOTS = {
    "summary": (
        "deployment_targets", "build_image_start", "reachable_port_or_path",
        "runtime_dependencies_state", "execution_conflicts", "credential_exposure",
        "minimum_design_inputs",
    ),
    "detailed": (
        "deployment_targets", "build_image_start", "reachable_port_or_path",
        "runtime_dependencies_state", "execution_conflicts", "credential_exposure",
        "minimum_design_inputs", "configuration_timing", "lifecycle_recovery",
        "observability", "deployment_evidence", "readiness_verdict",
    ),
}


class ContractsStageTests(unittest.TestCase):
    @staticmethod
    def payload(handoff: dict, analysis_mode: str, **overrides: object) -> dict:
        """Build a valid contracts payload from the handoff's pushed survey.

        Report slots either reuse a predecessor fact (assign_report_slot_facts,
        the same greedy exclusive assignment the server's survey uses to decide
        which slots need fresh evidence) or ground a fresh Contracts claim from
        the survey's per-slot observation (stage_input.survey.observations,
        tagged category="report_slot:<slot_id>"). No independent read_evidence
        call is needed for routine per-slot grounding.
        """
        slots = REPORT_SLOTS[analysis_mode]
        fact_statuses = handoff["stage_input"]["fact_statuses"]
        assignment = assign_report_slot_facts(list(slots), fact_statuses)
        survey_observations = {
            observation["category"].split(":", 1)[1]: observation["observation_ref"]
            for observation in handoff["stage_input"]["survey"]["observations"]
            if observation["category"].startswith("report_slot:")
        }
        claim_slots = [slot_id for slot_id in slots if assignment[slot_id] is None]
        value = {
            "schema_version": 1,
            "stage": "contracts",
            "evidence": [
                {"alias": f"slot-{slot_id}", "observation_ref": survey_observations[slot_id]}
                for slot_id in claim_slots
            ],
            "claims": [
                {"id": f"claim-{slot_id}", "status": "confirmed", "evidence_aliases": [f"slot-{slot_id}"]}
                for slot_id in claim_slots
            ],
            "rule_applications": [],
            "discovery_fact_refs": handoff["stage_input"]["discovery_fact_refs"],
            "execution_fact_refs": handoff["stage_input"]["execution_fact_refs"],
            "relationship_fact_refs": handoff["stage_input"]["relationship_fact_refs"],
            "boundaries_fact_refs": handoff["stage_input"]["boundaries_fact_refs"],
            "report_slots": [
                {
                    "id": slot_id,
                    "status": "confirmed",
                    "fact_refs": [assignment[slot_id]] if assignment[slot_id] is not None else [],
                    "claim_ids": [f"claim-{slot_id}"] if slot_id in claim_slots else [],
                }
                for slot_id in slots
            ],
        }
        value.update(overrides)
        return value

    def start_with_boundaries(self, mode: str) -> tuple[object, object, dict]:
        helper = BoundariesStageTests()
        relationship_helper = RelationshipsStageTests()
        temporary, server, _, discovery, execution = relationship_helper.start_with_execution(mode)
        observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
        self.assertFalse(failed, observation)
        relationships, failed = server.tool_call(
            "submit_relationships",
            {
                "payload": relationship_helper.relationships_payload(
                    observation["observation_ref"],
                    discovery["stage_input"]["discovery_fact_refs"],
                    execution["stage_input"]["execution_fact_refs"],
                ),
            },
        )
        self.assertFalse(failed, relationships)
        observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
        self.assertFalse(failed, observation)
        boundaries, failed = server.tool_call(
            "submit_boundaries",
            {"payload": helper.payload(observation["observation_ref"], relationships)},
        )
        self.assertFalse(failed, boundaries)
        return temporary, server, boundaries

    def test_submits_all_report_slots_through_five_real_stages_in_both_modes(self) -> None:
        for mode in REPORT_SLOTS:
            with self.subTest(mode=mode):
                temporary, server, boundaries = self.start_with_boundaries(mode)
                with temporary:
                    result, failed = server.tool_call(
                        "submit_contracts",
                        {"payload": self.payload(boundaries, mode)},
                    )

                self.assertFalse(failed, result)
                self.assertEqual(result["current_stage"], "finalize")
                self.assertEqual(result["mode"], mode)
                self.assertEqual(result["accepted_output"]["report_slot_ids"], list(REPORT_SLOTS[mode]))
                self.assertEqual(boundaries["stage_input"]["required_report_slot_ids"], list(REPORT_SLOTS[mode]))
                self.assertNotIn("app.py", json.dumps(result, sort_keys=True))

    def test_rejects_missing_or_dangling_report_slots_without_loading_finalize(self) -> None:
        temporary, server, boundaries = self.start_with_boundaries("summary")
        with temporary:
            payload = self.payload(boundaries, "summary")
            rejected, failed = server.tool_call(
                "submit_contracts",
                {
                    "payload": self.payload(
                        boundaries, "summary", report_slots=payload["report_slots"][:-1],
                    ),
                },
            )

        self.assertTrue(failed)
        self.assertEqual(server.session.current_stage, "contracts")
        self.assertEqual(server.session.revision, boundaries["revision"])
        self.assertNotIn("current_stage", json.dumps(rejected, sort_keys=True))

    def test_rejects_a_conflicted_slot_without_conflicted_fact_or_claim(self) -> None:
        temporary, server, boundaries = self.start_with_boundaries("summary")
        with temporary:
            payload = self.payload(boundaries, "summary")
            for slot in payload["report_slots"]:
                if slot["id"] == "execution_conflicts":
                    slot["status"] = "conflicted"
            rejected, failed = server.tool_call(
                "submit_contracts",
                {"payload": payload},
            )

        self.assertTrue(failed)
        self.assertEqual(server.session.current_stage, "contracts")
        self.assertNotIn("conflicted", json.dumps(rejected, sort_keys=True))

    def test_rejects_a_predecessor_fact_reused_across_report_slots(self) -> None:
        temporary, server, boundaries = self.start_with_boundaries("summary")
        with temporary:
            payload = self.payload(boundaries, "summary")
            deployment_fact = next(slot for slot in payload["report_slots"] if slot["id"] == "deployment_targets")["fact_refs"]
            self.assertTrue(deployment_fact)
            credential_slot = next(slot for slot in payload["report_slots"] if slot["id"] == "credential_exposure")
            credential_slot["fact_refs"] = deployment_fact
            rejected, failed = server.tool_call(
                "submit_contracts", {"payload": payload}
            )

        self.assertTrue(failed)
        self.assertEqual(server.session.current_stage, "contracts")
        self.assertNotIn("current_stage", json.dumps(rejected, sort_keys=True))

    def test_rejects_model_provided_mode_drift(self) -> None:
        temporary, server, boundaries = self.start_with_boundaries("summary")
        with temporary:
            rejected, failed = server.tool_call(
                "submit_contracts",
                {
                    "payload": self.payload(boundaries, "summary", mode="detailed"),
                },
            )

        self.assertTrue(failed)
        self.assertEqual(server.session.current_stage, "contracts")
        self.assertNotIn("detailed", json.dumps(rejected, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
