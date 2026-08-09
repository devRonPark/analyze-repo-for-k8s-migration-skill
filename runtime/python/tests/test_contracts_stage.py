import json
import unittest

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

SLOT_FACT_SOURCE = {
    "deployment_targets": ("discovery_fact_refs", 0),
    "build_image_start": ("execution_fact_refs", 0),
    "runtime_dependencies_state": ("relationship_fact_refs", 0),
    "execution_conflicts": ("boundaries_fact_refs", 0),
    "minimum_design_inputs": ("boundaries_fact_refs", 1),
    "lifecycle_recovery": ("boundaries_fact_refs", 2),
    "readiness_verdict": ("boundaries_fact_refs", 3),
}


def current_claim_slots(analysis_mode: str) -> tuple[str, ...]:
    return tuple(slot_id for slot_id in REPORT_SLOTS[analysis_mode] if slot_id not in SLOT_FACT_SOURCE)


class ContractsStageTests(unittest.TestCase):
    @staticmethod
    def envelope(handoff: dict) -> dict:
        return BoundariesStageTests.envelope(handoff)

    @staticmethod
    def payload(observation_refs: list[str], handoff: dict, analysis_mode: str, **overrides: object) -> dict:
        slots = REPORT_SLOTS[analysis_mode]
        claim_slots = current_claim_slots(analysis_mode)
        if len(observation_refs) != len(claim_slots):
            raise ValueError("one independent observation is required per current report claim")
        value = {
            "schema_version": 1,
            "stage": "contracts",
            "evidence": [
                {"alias": f"slot-{index}", "observation_ref": observation_ref}
                for index, observation_ref in enumerate(observation_refs)
            ],
            "claims": [
                {"id": f"claim-{slot_id}", "status": "confirmed", "evidence_aliases": [f"slot-{index}"]}
                for index, slot_id in enumerate(claim_slots)
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
                    "fact_refs": [handoff["stage_input"][SLOT_FACT_SOURCE[slot_id][0]][SLOT_FACT_SOURCE[slot_id][1]]]
                    if slot_id in SLOT_FACT_SOURCE else [],
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
                **self.envelope(execution),
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
            {**self.envelope(relationships), "payload": helper.payload(observation["observation_ref"], relationships)},
        )
        self.assertFalse(failed, boundaries)
        return temporary, server, boundaries

    def contract_observations(self, server: object, analysis_mode: str) -> list[str]:
        references: list[str] = []
        for index, _ in enumerate(current_claim_slots(analysis_mode), start=1):
            observation, failed = server.tool_call("read_evidence", {"path": f"contract-evidence-{index}.txt"})
            self.assertFalse(failed, observation)
            references.append(observation["observation_ref"])
        return references

    def test_submits_all_report_slots_through_five_real_stages_in_both_modes(self) -> None:
        for mode in REPORT_SLOTS:
            with self.subTest(mode=mode):
                temporary, server, boundaries = self.start_with_boundaries(mode)
                with temporary:
                    observations = self.contract_observations(server, mode)
                    result, failed = server.tool_call(
                        "submit_contracts",
                        {**self.envelope(boundaries), "payload": self.payload(observations, boundaries, mode)},
                    )

                self.assertFalse(failed, result)
                self.assertEqual(result["next_skill"], "analyze-k8s-finalize")
                self.assertEqual(result["mode"], mode)
                self.assertEqual(result["accepted_output"]["report_slot_ids"], list(REPORT_SLOTS[mode]))
                self.assertEqual(boundaries["stage_input"]["required_report_slot_ids"], list(REPORT_SLOTS[mode]))
                self.assertNotIn("app.py", json.dumps(result, sort_keys=True))

    def test_rejects_missing_or_dangling_report_slots_without_loading_finalize(self) -> None:
        temporary, server, boundaries = self.start_with_boundaries("summary")
        with temporary:
            observations = self.contract_observations(server, "summary")
            payload = self.payload(observations, boundaries, "summary")
            rejected, failed = server.tool_call(
                "submit_contracts",
                {
                    **self.envelope(boundaries),
                    "payload": self.payload(
                        observations, boundaries, "summary", report_slots=payload["report_slots"][:-1],
                    ),
                },
            )

        self.assertTrue(failed)
        self.assertEqual(server.session.current_stage, "contracts")
        self.assertEqual(server.session.revision, boundaries["revision"])
        self.assertNotIn("analyze-k8s-finalize", json.dumps(rejected, sort_keys=True))

    def test_rejects_a_conflicted_slot_without_conflicted_fact_or_claim(self) -> None:
        temporary, server, boundaries = self.start_with_boundaries("summary")
        with temporary:
            observations = self.contract_observations(server, "summary")
            payload = self.payload(observations, boundaries, "summary")
            for slot in payload["report_slots"]:
                if slot["id"] == "execution_conflicts":
                    slot["status"] = "conflicted"
            rejected, failed = server.tool_call(
                "submit_contracts",
                {**self.envelope(boundaries), "payload": payload},
            )

        self.assertTrue(failed)
        self.assertEqual(server.session.current_stage, "contracts")
        self.assertNotIn("conflicted", json.dumps(rejected, sort_keys=True))

    def test_rejects_a_predecessor_fact_reused_across_report_slots(self) -> None:
        temporary, server, boundaries = self.start_with_boundaries("summary")
        with temporary:
            observations = self.contract_observations(server, "summary")
            payload = self.payload(observations, boundaries, "summary")
            deployment_fact = next(slot for slot in payload["report_slots"] if slot["id"] == "deployment_targets")["fact_refs"]
            credential_slot = next(slot for slot in payload["report_slots"] if slot["id"] == "credential_exposure")
            credential_slot["fact_refs"] = deployment_fact
            rejected, failed = server.tool_call(
                "submit_contracts", {**self.envelope(boundaries), "payload": payload}
            )

        self.assertTrue(failed)
        self.assertEqual(server.session.current_stage, "contracts")
        self.assertNotIn("analyze-k8s-finalize", json.dumps(rejected, sort_keys=True))

    def test_rejects_model_provided_mode_drift(self) -> None:
        temporary, server, boundaries = self.start_with_boundaries("summary")
        with temporary:
            observations = self.contract_observations(server, "detailed")
            rejected, failed = server.tool_call(
                "submit_contracts",
                {
                    **self.envelope(boundaries),
                    "payload": self.payload(observations, boundaries, "detailed", mode="detailed"),
                },
            )

        self.assertTrue(failed)
        self.assertEqual(server.session.current_stage, "contracts")
        self.assertNotIn("detailed", json.dumps(rejected, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
