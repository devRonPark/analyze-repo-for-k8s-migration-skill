import unittest
from unittest.mock import patch

from analysis_pipeline.mcp_server import Server
from analysis_pipeline.stage_contracts import _require_contract_fields, _validate_relationship_edges, validate_boundaries_payload, validate_contracts_payload


class ContractsCorrectionProtocolTests(unittest.TestCase):
    def test_missing_stage_fields_are_returned_together(self) -> None:
        with patch("analysis_pipeline.stage_contracts.client_payload_required_fields", return_value={"a", "b", "c"}):
            with self.assertRaisesRegex(ValueError, "missing boundaries payload field\\(s\\): a, b, c"):
                _require_contract_fields("boundaries", {})

    def test_boundary_status_error_names_all_invalid_wire_fields(self) -> None:
        payload = {
            "stage": "boundaries", "evidence": [{}], "claims": [{}],
            "discovery_fact_refs": [], "execution_fact_refs": [], "relationship_fact_refs": [],
            "workload_units": [{
                "id": "unit_1", "process_ids": ["process_1"], "candidate_ids": [],
                "start_definition_status": "bad", "independent_lifecycle_status": "bad", "boundary_status": "bad",
                "lifecycle": "continuous", "state_decision": "unknown", "deployable": False,
                "deployability_status": "inferred", "boundary_claim_ids": [], "lifecycle_claim_ids": [],
                "state_claim_ids": [], "deployability_claim_ids": [],
            }],
        }
        with patch("analysis_pipeline.stage_contracts._require_contract_fields"), patch(
            "analysis_pipeline.stage_contracts.normalize_submission_payload", return_value=(payload, {})
        ), patch("analysis_pipeline.stage_contracts.workload_unit_contract", return_value={
            "id": "identifier", "process_ids": [], "candidate_ids": [], "start_definition_status": "confirmed|unknown|conflicted",
            "independent_lifecycle_status": "confirmed|unknown|conflicted", "boundary_status": "confirmed|unknown|conflicted",
            "lifecycle": "continuous|worker", "state_decision": "unknown|stateless", "deployable": "boolean",
            "deployability_status": "confirmed|inferred", "boundary_claim_ids": [], "lifecycle_claim_ids": [],
            "state_claim_ids": [], "deployability_claim_ids": [],
        }), patch("analysis_pipeline.stage_contracts.validate_workload_grouping", return_value=set()):
            with self.assertRaisesRegex(ValueError, "start_definition_status, independent_lifecycle_status, boundary_status"):
                validate_boundaries_payload(payload, None, None, {}, [], [], [], ["process_1"], [])

    def test_relationship_edge_fields_are_reported_together(self) -> None:
        edge = {
            "id": "edge_1", "source_process_id": "process_1", "target_id": "target_1",
            "target_kind": "external_system", "dependency_type": "not a type", "mechanism": "human prose",
            "endpoint_name": "also prose", "required_for_function": "confirmed", "startup_use": "confirmed",
            "management_boundary": "repository_managed", "timing": "runtime", "execution_location": "not a location",
            "claim_ids": ["claim_1"], "status": "confirmed",
        }
        with patch("analysis_pipeline.stage_contracts.relationship_edge_contract", return_value={
            "id": "identifier", "source_process_id": "identifier", "target_id": "identifier", "target_kind": "process|external_system",
            "dependency_type": "service|data_store", "mechanism": "identifier", "endpoint_name": "identifier",
            "required_for_function": "confirmed|unknown", "startup_use": "confirmed|unknown", "management_boundary": "repository_managed|unknown",
            "timing": "runtime|unknown", "execution_location": "server_process|unknown", "claim_ids": [], "status": "confirmed|unknown",
        }):
            with self.assertRaisesRegex(ValueError, "mechanism.*endpoint_name.*dependency_type.*execution_location"):
                _validate_relationship_edges([edge], [{"id": "claim_1", "status": "confirmed"}], ["process_1"])

    def test_slot_set_mismatch_reports_all_unexpected_and_missing_ids(self) -> None:
        payload = {
            "evidence": [{}],
            "claims": [{}],
            "discovery_fact_refs": [],
            "execution_fact_refs": [],
            "relationship_fact_refs": [],
            "boundaries_fact_refs": [],
            "report_slots": [
                {"id": "invented_slot"},
                {"id": "another_invented_slot"},
            ],
        }
        with patch("analysis_pipeline.stage_contracts._require_contract_fields"), patch(
            "analysis_pipeline.stage_contracts.normalize_submission_payload", return_value=(payload, {})
        ), patch("analysis_pipeline.stage_contracts.required_report_slot_ids", return_value=["required_a", "required_b"]):
            with self.assertRaisesRegex(
                ValueError,
                "unexpected: another_invented_slot, invented_slot; missing: required_a, required_b",
            ):
                validate_contracts_payload(
                    payload,
                    registry=None,
                    snapshot=None,
                    binding={},
                    mode="summary",
                    discovery_fact_refs=[],
                    execution_fact_refs=[],
                    relationship_fact_refs=[],
                    boundaries_fact_refs=[],
                    fact_statuses={},
                )

    def test_finalize_before_contracts_names_the_only_valid_next_action(self) -> None:
        server = Server()
        server.session.current_stage = "contracts"
        with patch.object(server.session, "assert_active", side_effect=ValueError("stage_order")):
            result, failed = server._dispatch("finalize_analysis", {})

        self.assertTrue(failed)
        self.assertEqual(result["code"], "stage_order")
        self.assertIn("submit_contracts", result["issues"][0])


if __name__ == "__main__":
    unittest.main()
