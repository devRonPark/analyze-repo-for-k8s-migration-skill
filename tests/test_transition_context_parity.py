"""D13 structural successor-context parity characterization tests."""
from __future__ import annotations

import copy
import json
import unittest

from scripts import run_opencode_acceptance as adapter


SKILL = "analyze-k8s-execution"


def _handoff(*, host: bool = False, stage_input: object = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "accepted",
        "completed_stage": "discovery",
        "next_skill": SKILL,
        "accepted_output": {"accepted": True},
    }
    if stage_input is not None:
        payload["stage_input"] = stage_input
    if host:
        payload["host_continuation"] = {
            "transition_owner": "host",
            "requested_skill": SKILL,
            "skill_load": "completed",
            "skill_content": "# Execution\nUse the incoming handoff only.\n",
        }
    return {
        "name": "analysis_submit_discovery",
        "state": {"time": {"start": 100, "end": 120}, "output": json.dumps(payload)},
    }


def _native_skill(*, name: str = SKILL) -> dict[str, object]:
    return {
        "name": "skill",
        "state": {
            "input": {"name": name},
            "output": "# Execution\nUse the incoming handoff only.\n",
            "time": {"start": 140, "end": 150},
        },
    }


def _action() -> dict[str, object]:
    return {
        "name": "analysis_read_evidence",
        "state": {"time": {"start": 180, "end": 190}, "output": json.dumps({"status": "completed"})},
    }


def _record(*, host: bool = False, stage_input: object = None) -> dict[str, object]:
    transition = adapter.trace_stage_transitions(
        [_handoff(host=host, stage_input=stage_input), _native_skill(), _action()],
        [],
        terminal_reason=None,
    )[0]
    return transition["transition_context"]


class TransitionContextParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = _record(stage_input={"mode": "summary", "candidate_ids": ["candidate-a"]})

    def test_exact_parity_is_equivalent(self) -> None:
        comparison = adapter.compare_transition_contexts(self.model, copy.deepcopy(self.model))

        self.assertEqual(comparison["context_parity"], "equivalent")
        self.assertTrue(all(value == "same" or value == "unavailable" for value in comparison["dimensions"].values()))

    def test_host_and_native_skill_sources_are_counted_separately(self) -> None:
        host = _record(host=True, stage_input={"mode": "summary", "candidate_ids": ["candidate-a"]})
        comparison = adapter.compare_transition_contexts(self.model, host)

        self.assertEqual(host["skill"]["occurrences"], 2)
        self.assertEqual(comparison["dimensions"]["skill_multiplicity"], "different")
        self.assertEqual(comparison["context_parity"], "different")

    def test_duplicated_stage_input_is_a_mismatch(self) -> None:
        host = copy.deepcopy(self.model)
        host["stage_input"]["occurrences"] = 2

        self.assertEqual(adapter.compare_transition_contexts(self.model, host)["dimensions"]["stage_input_multiplicity"], "different")

    def test_missing_stage_input_is_a_mismatch(self) -> None:
        missing = _record(stage_input=None)

        self.assertFalse(missing["stage_input"]["observed"])
        self.assertEqual(adapter.compare_transition_contexts(self.model, missing)["context_parity"], "different")

    def test_message_role_mismatch_is_not_silently_equivalent(self) -> None:
        host = copy.deepcopy(self.model)
        host["skill"]["sources"][0]["role"] = "user"

        comparison = adapter.compare_transition_contexts(self.model, host)
        self.assertEqual(comparison["dimensions"]["message_role"], "different")
        self.assertEqual(comparison["context_parity"], "different")

    def test_ordering_mismatch_is_reported_separately(self) -> None:
        host = copy.deepcopy(self.model)
        host["ordering"] = ["accepted_handoff", "first_successor_action", "native_skill_tool_result"]

        self.assertEqual(adapter.compare_transition_contexts(self.model, host)["dimensions"]["message_ordering"], "different")

    def test_extra_turn_boundary_is_observable(self) -> None:
        host = copy.deepcopy(self.model)
        host["turn_boundary"]["native_model_turns_before_first_action"] = 2

        self.assertEqual(adapter.compare_transition_contexts(self.model, host)["dimensions"]["turn_boundary"], "different")

    def test_context_size_difference_is_quantitative_not_alone_a_semantic_failure(self) -> None:
        host = copy.deepcopy(self.model)
        host["context_size_proxy"]["serialized_chars"] += 100

        comparison = adapter.compare_transition_contexts(self.model, host)
        self.assertEqual(comparison["dimensions"]["context_size"], "different")
        self.assertEqual(comparison["context_parity"], "equivalent")

    def test_missing_artifact_is_unavailable_not_equal(self) -> None:
        comparison = adapter.compare_transition_contexts(self.model, None)

        self.assertEqual(comparison["context_parity"], "unavailable")

    def test_existing_transition_trace_still_contains_prior_observability(self) -> None:
        transition = adapter.trace_stage_transitions(
            [_handoff(stage_input={"mode": "summary"}), _native_skill(), _action()],
            [],
            terminal_reason=None,
        )[0]

        self.assertEqual(transition["skill_load"]["status"], "observed")
        self.assertEqual(transition["first_next_stage_action"]["name"], "read_evidence")
        self.assertIn("transition_context", transition)


if __name__ == "__main__":
    unittest.main()
