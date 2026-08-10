from pathlib import Path
import sys
import unittest


RUNTIME_PYTHON = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME_PYTHON))

from analysis_pipeline import ANALYSIS_STAGES, FINAL_STAGE, canonical_json, create_state, derive_evidence_id, finalize, normalize_submission_payload, reopen, submit
from analysis_pipeline.validation import derive_runtime_process_id


BINDING = {
    "binding_id": "bind-1",
    "target_realpath": "/target",
    "target_snapshot_hash": "snapshot-1",
    "skill_manifest_hash": "skill-1",
    "required_rule_ids": ["rule.discovery"],
}


def valid_payload(stage: str, *, override: dict | None = None) -> dict:
    evidence = {
        "location": f"{stage}.md",
        "range": "1-1",
        "status": "confirmed",
        "content_fingerprint": f"{stage}-fingerprint",
        "redacted": True,
    }
    evidence_id = derive_evidence_id({"snapshot_hash": BINDING["target_snapshot_hash"], **evidence})
    base = {
        "stage": stage,
        "claims": [{"id": f"{stage}-claim", "status": "confirmed", "evidence_ids": [evidence_id]}],
        "evidence_ids": [evidence_id],
        "evidence_inputs": {evidence_id: evidence},
        "rule_applications": [],
    }
    stage_data = {
        "discovery": {
            "signals": ["signal-1"],
            "candidate_ids": ["candidate-1"],
            "decisions": ["decision-1"],
            "rule_applications": [
                {
                    "rule_id": "rule.discovery",
                    "evidence_ids": [evidence_id],
                    "process_or_candidate_ids": ["candidate-1"],
                    "decision_id": "decision-1",
                }
            ],
        },
        "execution": {
            "runtime_processes": [{
                "id": derive_runtime_process_id({"candidate_ids": ["candidate-1"], "role": "unknown", "execution_pattern": "unknown", "semantic_fact_refs": []}),
                "candidate_ids": ["candidate-1"],
                "role": "unknown",
                "execution_pattern": "unknown",
                "semantic_fact_refs": [],
            }],
            "process_ids": [derive_runtime_process_id({"candidate_ids": ["candidate-1"], "role": "unknown", "execution_pattern": "unknown", "semantic_fact_refs": []})],
        },
        "relationships": {"graph_edge_ids": ["edge-1"]},
        "boundaries": {
            "unit_ids": ["unit-1"],
            "deployable_unit_ids": ["unit-1"],
            "decisions": ["decision-1"],
        },
        "contracts": {"contract_ids": ["contract-1"]},
        "finalize": {"decisions": ["decision-1"]},
    }[stage]
    payload = {**base, **stage_data}
    if override:
        payload.update(override)
    return payload


class PipelineStateTests(unittest.TestCase):
    @staticmethod
    def _issued_observation(*, status: str = "confirmed") -> dict:
        return {
            "location": "Dockerfile", "range": "17-21", "status": status,
            "content_fingerprint": "server-derived-fingerprint", "redacted": True,
        }

    @staticmethod
    def _alias_submission(observation_ref: str = "obs_issued") -> dict:
        return {
            "schema_version": 1,
            "stage": "discovery",
            "evidence": [{"alias": "docker_start", "observation_ref": observation_ref}],
            "claims": [{"id": "claim-start", "status": "confirmed", "evidence_aliases": ["docker_start"]}],
            "rule_applications": [],
            "signals": ["signal-1"], "candidate_ids": ["candidate-1"], "decisions": ["decision-1"],
        }

    def test_normalizes_local_aliases_to_server_derived_evidence_ids(self) -> None:
        normalized, evidence = normalize_submission_payload(
            self._alias_submission(), {"obs_issued": self._issued_observation()}, BINDING
        )
        evidence_id = next(iter(evidence))
        self.assertEqual(normalized["claims"][0]["evidence_ids"], [evidence_id])
        self.assertEqual(normalized["evidence_ids"], [evidence_id])
        self.assertNotIn("evidence", normalized)
        self.assertNotIn("evidence_aliases", normalized["claims"][0])

    def test_rejects_client_owned_evidence_fields_and_alias_misuse(self) -> None:
        client_evidence = self._alias_submission()
        client_evidence["evidence_ids"] = []
        with self.assertRaisesRegex(ValueError, "client evidence"):
            normalize_submission_payload(client_evidence, {"obs_issued": self._issued_observation()}, BINDING)

        duplicate = self._alias_submission()
        duplicate["evidence"].append({"alias": "docker_start", "observation_ref": "obs_other"})
        with self.assertRaisesRegex(ValueError, "duplicate alias"):
            normalize_submission_payload(duplicate, {"obs_issued": self._issued_observation(), "obs_other": self._issued_observation()}, BINDING)

        unreferenced = self._alias_submission()
        unreferenced["claims"] = []
        with self.assertRaisesRegex(ValueError, "unreferenced observation"):
            normalize_submission_payload(unreferenced, {"obs_issued": self._issued_observation()}, BINDING)

    def test_canonical_json_and_evidence_ids_are_stable(self) -> None:
        self.assertEqual(canonical_json({"b": 1, "a": [2, {"c": 3}]}), '{"a":[2,{"c":3}],"b":1}')
        self.assertEqual(
            derive_evidence_id({"snapshot_hash": "snapshot-1", "location": "a", "range": "1-1", "status": "confirmed", "content_fingerprint": "x"}),
            derive_evidence_id({"content_fingerprint": "x", "status": "confirmed", "range": "1-1", "location": "a", "snapshot_hash": "snapshot-1"}),
        )

    def test_accepts_five_submitted_stages_then_finalizes_without_submit_finalize(self) -> None:
        state = create_state(BINDING)
        for stage in ANALYSIS_STAGES:
            state = submit(state, stage, valid_payload(stage), state.revision, state.digest())
        self.assertEqual(state.current_stage, FINAL_STAGE)
        self.assertEqual(set(state.outputs), set(ANALYSIS_STAGES))
        completed = finalize(state, state.revision, state.digest())
        self.assertTrue(completed.finalized)
        with self.assertRaisesRegex(ValueError, "finalized"):
            finalize(completed, completed.revision, completed.digest())

    def test_rejects_skipped_duplicate_stale_and_server_owned_binding_submissions(self) -> None:
        state = create_state(BINDING)
        with self.assertRaisesRegex(ValueError, "stage order"):
            submit(state, "execution", valid_payload("execution"), state.revision, state.digest())

        state = submit(state, "discovery", valid_payload("discovery"), state.revision, state.digest())

        with self.assertRaisesRegex(ValueError, "stage order|duplicate"):
            submit(state, "discovery", valid_payload("discovery"), state.revision, state.digest())
        with self.assertRaisesRegex(ValueError, "stale"):
            submit(state, "execution", valid_payload("execution"), state.revision - 1, state.digest())
        with self.assertRaisesRegex(ValueError, "binding"):
            submit(state, "execution", valid_payload("execution", override={"binding": "other"}), state.revision, state.digest())

    def test_reopen_invalidates_later_outputs_and_evidence(self) -> None:
        state = create_state(BINDING)
        for stage in ANALYSIS_STAGES[:4]:
            state = submit(state, stage, valid_payload(stage), state.revision, state.digest())

        reopened = reopen(state, "execution", "new evidence arrived", state.revision, state.digest())
        self.assertEqual(reopened.current_stage, "execution")
        self.assertNotIn("relationships", reopened.outputs)
        self.assertNotIn("boundaries", reopened.outputs)
        self.assertNotIn("execution", reopened.outputs)
        self.assertEqual(sorted(reopened.evidence.keys()), sorted(reopened.outputs["discovery"]["evidence_ids"]))
        with self.assertRaisesRegex(ValueError, "back-edge|reopen"):
            reopen(reopened, "finalize", "x", reopened.revision, reopened.digest())

    def test_rejects_dangling_evidence_unknown_claim_without_absence_and_secret_bearing_inputs(self) -> None:
        state = create_state(BINDING)
        with self.assertRaisesRegex(ValueError, "evidence"):
            submit(
                state,
                "discovery",
                {
                    "stage": "discovery",
                    "signals": ["signal-1"],
                    "candidate_ids": ["candidate-1"],
                    "decisions": ["decision-1"],
                    "claims": [{"id": "c-1", "status": "confirmed", "evidence_ids": ["missing"]}],
                    "evidence_ids": [],
                    "evidence_inputs": {},
                    "rule_applications": [],
                },
                state.revision,
                state.digest(),
            )

        with self.assertRaisesRegex(ValueError, "unknown claim|absence"):
            submit(
                state,
                "discovery",
                valid_payload(
                    "discovery",
                    override={
                        "claims": [{"id": "c-1", "status": "unknown", "evidence_ids": [], "scope": "repo", "blocked_decision": "decision-1"}],
                        "rule_applications": [],
                    },
                ),
                state.revision,
                state.digest(),
            )

        forged = valid_payload("discovery")
        forged["evidence_ids"] = ["ev_forged"]
        forged["claims"] = [{"id": "c-1", "status": "confirmed", "evidence_ids": ["ev_forged"]}]
        forged["rule_applications"] = [
            {
                "rule_id": "rule.discovery",
                "evidence_ids": ["ev_forged"],
                "process_or_candidate_ids": ["candidate-1"],
                "decision_id": "decision-1",
            }
        ]
        forged["evidence_inputs"] = {
            "ev_forged": {
                "location": "config.env",
                "range": "1-1",
                "status": "confirmed",
                "content_fingerprint": "password=hunter2",
                "redacted": True,
                "raw_content": "password=hunter2",
            }
        }
        with self.assertRaisesRegex(ValueError, "forged|secret|unknown evidence field"):
            submit(state, "discovery", forged, state.revision, state.digest())

    def test_rejects_duplicate_rule_applications_and_finalize_validation_failures(self) -> None:
        state = create_state(BINDING)
        duplicated_rules = valid_payload(
            "discovery",
            override={
                "rule_applications": [
                    {
                        "rule_id": "rule.discovery",
                        "evidence_ids": [valid_payload("discovery")["evidence_ids"][0]],
                        "process_or_candidate_ids": ["candidate-1"],
                        "decision_id": "decision-1",
                    },
                    {
                        "rule_id": "rule.discovery",
                        "evidence_ids": [valid_payload("discovery")["evidence_ids"][0]],
                        "process_or_candidate_ids": ["candidate-1"],
                        "decision_id": "decision-1",
                    },
                ]
            },
        )
        with self.assertRaisesRegex(ValueError, "duplicate rule application"):
            submit(state, "discovery", duplicated_rules, state.revision, state.digest())

        missing_rule_binding = {**BINDING, "required_rule_ids": ["rule.discovery", "rule.boundaries"]}
        state = create_state(missing_rule_binding)
        for stage in ANALYSIS_STAGES:
            state = submit(state, stage, valid_payload(stage), state.revision, state.digest())
        with self.assertRaisesRegex(ValueError, "mandatory rule"):
            finalize(state, state.revision, state.digest())

    def test_rejects_dangling_rule_subjects_and_invalid_deployable_unit_cardinality(self) -> None:
        state = create_state(BINDING)
        invalid_subject = valid_payload(
            "discovery",
            override={
                "rule_applications": [
                    {
                        "rule_id": "rule.discovery",
                        "evidence_ids": [valid_payload("discovery")["evidence_ids"][0]],
                        "process_or_candidate_ids": ["candidate-missing"],
                        "decision_id": "decision-1",
                    }
                ]
            },
        )
        with self.assertRaisesRegex(ValueError, "subject|candidate"):
            submit(state, "discovery", invalid_subject, state.revision, state.digest())

        state = submit(create_state(BINDING), "discovery", valid_payload("discovery"), 0, create_state(BINDING).digest())
        state = submit(state, "execution", valid_payload("execution"), state.revision, state.digest())
        state = submit(state, "relationships", valid_payload("relationships"), state.revision, state.digest())
        with self.assertRaisesRegex(ValueError, "deployable|unit"):
            submit(
                state,
                "boundaries",
                valid_payload("boundaries", override={"unit_ids": ["unit-1"], "deployable_unit_ids": ["unit-2"]}),
                state.revision,
                state.digest(),
            )

    def test_rejects_premature_finalization(self) -> None:
        state = create_state(BINDING)
        with self.assertRaisesRegex(ValueError, "complete|incomplete"):
            finalize(state, state.revision, state.digest())


if __name__ == "__main__":
    unittest.main()
