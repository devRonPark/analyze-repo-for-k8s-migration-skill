import json
import unittest

from runtime.python.tests.test_boundaries_stage import BoundariesStageTests
from runtime.python.tests.test_contracts_stage import ContractsStageTests


class BoundariesRecoveryTests(unittest.TestCase):
    """D08's narrow server-owned recovery tracer bullet."""

    def start_with_relationships(self):
        return BoundariesStageTests().start_with_relationships()

    @staticmethod
    def invalid_payload(observation_ref, relationships, value="invalid-status", **overrides):
        payload = BoundariesStageTests.payload(observation_ref, relationships, **overrides)
        payload["workload_units"][0]["boundary_status"] = value
        return payload

    def test_normal_boundaries_success_does_not_recover(self):
        temporary, server, _, relationships = self.start_with_relationships()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            result, failed = server.tool_call(
                "submit_boundaries",
                {"payload": BoundariesStageTests.payload(observation["observation_ref"], relationships)},
            )

        self.assertFalse(failed, result)
        self.assertNotIn("recovery", result)
        self.assertEqual(server.session.current_stage, "contracts")

    def test_ordinary_correction_accepts_normally_without_recovery(self):
        temporary, server, _, relationships = self.start_with_relationships()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            rejected, failed = server.tool_call(
                "submit_boundaries",
                {"payload": self.invalid_payload(observation["observation_ref"], relationships)},
            )
            accepted, accepted_failed = server.tool_call(
                "submit_boundaries",
                {"payload": BoundariesStageTests.payload(observation["observation_ref"], relationships)},
            )

        self.assertTrue(failed, rejected)
        self.assertFalse(accepted_failed, accepted)
        self.assertNotIn("recovery", accepted)

    def test_repeated_unchanged_boundary_error_recovers_as_r1(self):
        temporary, server, _, relationships = self.start_with_relationships()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            payload = self.invalid_payload(observation["observation_ref"], relationships)
            attempts = [server.tool_call("submit_boundaries", {"payload": payload}) for _ in range(4)]

        for result, failed in attempts[:3]:
            self.assertTrue(failed, result)
        recovered, failed = attempts[3]
        self.assertFalse(failed, recovered)
        self.assertEqual(recovered["recovery"]["class"], "R1")
        self.assertTrue(recovered["recovery"]["degraded"])
        self.assertNotIn("invalid-status", json.dumps(server.session.pipeline.outputs["boundaries"]))

    def test_changing_boundary_corrections_recover_as_r2(self):
        temporary, server, _, relationships = self.start_with_relationships()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            attempts = [
                server.tool_call(
                    "submit_boundaries",
                    {"payload": self.invalid_payload(observation["observation_ref"], relationships, f"invalid-{index}")},
                )
                for index in range(4)
            ]

        for result, failed in attempts[:3]:
            self.assertTrue(failed, result)
        recovered, failed = attempts[3]
        self.assertFalse(failed, recovered)
        self.assertEqual(recovered["recovery"]["class"], "R2")
        self.assertEqual([entry["relevant_changed"] for entry in recovered["recovery"]["attempts"]], [False, True, True, True])

    def test_recovery_can_use_a_server_survey_start_observation(self):
        temporary, server, target, relationships = self.start_with_relationships()
        with temporary:
            start = server.session.registry.issue_present(
                "boundaries", target / "app.py", 1, 1, "print('ready')"
            )["observation_ref"]
            server.session.boundaries_survey = [
                {**item, "status": "confirmed", "observation_ref": start}
                if item["category"] == "independent start definitions" else item
                for item in server.session.boundaries_survey
            ]
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            payload = self.invalid_payload(observation["observation_ref"], relationships)
            for _ in range(3):
                server.tool_call("submit_boundaries", {"payload": payload})
            recovered, failed = server.tool_call("submit_boundaries", {"payload": payload})

        self.assertFalse(failed, recovered)
        self.assertEqual(
            server.session.pipeline.outputs["boundaries"]["workload_units"][0]["start_definition_status"],
            "confirmed",
        )

    def test_recovery_fails_closed_without_required_trusted_absence_observations(self):
        temporary, server, _, relationships = self.start_with_relationships()
        with temporary:
            server.session.boundaries_survey = []
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            attempts = [
                server.tool_call("submit_boundaries", {"payload": self.invalid_payload(observation["observation_ref"], relationships)})
                for _ in range(4)
            ]

        result, failed = attempts[-1]
        self.assertTrue(failed, result)
        self.assertEqual(result["code"], "boundaries_recovery_unavailable")
        self.assertEqual(server.session.current_stage, "boundaries")
        self.assertNotIn("boundaries", server.session.pipeline.outputs)

    def test_recovery_never_promotes_rejected_model_assertion(self):
        temporary, server, _, relationships = self.start_with_relationships()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            payload = self.invalid_payload(
                observation["observation_ref"],
                relationships,
                claims=[
                    *BoundariesStageTests.payload(observation["observation_ref"], relationships)["claims"],
                    {"id": "claim-untrusted-solar-assertion", "status": "confirmed", "evidence_aliases": ["boundary"]},
                ],
            )
            attempts = [server.tool_call("submit_boundaries", {"payload": payload}) for _ in range(4)]

        recovered, failed = attempts[-1]
        self.assertFalse(failed, recovered)
        accepted = json.dumps(server.session.pipeline.outputs["boundaries"], sort_keys=True)
        self.assertNotIn("claim-untrusted-solar-assertion", accepted)

    def test_snapshot_change_wins_over_recovery(self):
        temporary, server, target, relationships = self.start_with_relationships()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            payload = self.invalid_payload(observation["observation_ref"], relationships)
            for _ in range(3):
                server.tool_call("submit_boundaries", {"payload": payload})
            (target / "app.py").write_text("changed\n", encoding="utf-8")
            result, failed = server.tool_call("submit_boundaries", {"payload": payload})

        self.assertTrue(failed, result)
        self.assertEqual(result["code"], "target_snapshot_changed")
        self.assertEqual(server.session.current_stage, "boundaries")

    def test_recovered_boundaries_hands_off_to_contracts_and_finalizes(self):
        temporary, server, _, relationships = self.start_with_relationships()
        with temporary:
            observation, failed = server.tool_call("read_evidence", {"path": "app.py"})
            self.assertFalse(failed, observation)
            payload = self.invalid_payload(observation["observation_ref"], relationships)
            for _ in range(3):
                server.tool_call("submit_boundaries", {"payload": payload})
            boundaries, failed = server.tool_call("submit_boundaries", {"payload": payload})
            self.assertFalse(failed, boundaries)
            contracts, failed = server.tool_call(
                "submit_contracts", {"payload": ContractsStageTests.payload(boundaries, "summary")}
            )
            self.assertFalse(failed, contracts)
            finalized, failed = server.tool_call("finalize_analysis", {})

        self.assertFalse(failed, finalized)
        self.assertEqual(finalized["status"], "finalized")


if __name__ == "__main__":
    unittest.main()
