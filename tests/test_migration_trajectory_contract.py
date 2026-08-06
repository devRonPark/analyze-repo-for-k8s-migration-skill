"""Lock the migration exploration trajectory evaluator contract (Task 6).

The evaluator reports metrics from a recorded run trajectory -- it never
enforces a fixed pass/fail threshold like "question_coverage >= 4" or
"duplicate_rate == 0", since those would overfit to one target repository
or one model. It distinguishes genuine recovery (a fresh observation
between a grounding error and the next submission) from a bare resubmit,
and never treats coverage counting as a substitute for grounded Evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from devtools.run_phase1_live_acceptance import evaluate_trajectory

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "adk_migration_trajectory"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def test_trajectory_reports_question_coverage_and_context_efficiency():
    result = evaluate_trajectory(load_fixture("valid-minimal.test.json"))

    assert result["required_question_disposition_rate"] == 1.0
    assert result["ungrounded_positive_value_count"] == 0
    assert result["unobserved_evidence_count"] == 0
    assert result["fresh_observation_after_grounding_error"] is True


def test_trajectory_confirms_the_first_tool_is_inspect_target():
    result = evaluate_trajectory(load_fixture("valid-minimal.test.json"))
    assert result["first_tool_is_inspect_target"] is True


def test_trajectory_reports_bounded_stop_compliance():
    result = evaluate_trajectory(load_fixture("valid-minimal.test.json"))
    assert result["bounded_stop_compliant"] is True


def test_trajectory_reports_context_projection_leak_free():
    result = evaluate_trajectory(load_fixture("valid-minimal.test.json"))
    assert result["context_projection_leak_free"] is True


def test_grounding_recovery_fixture_shows_a_genuine_fresh_observation():
    result = evaluate_trajectory(load_fixture("grounding-recovery.test.json"))
    assert result["fresh_observation_after_grounding_error"] is True


def test_first_tool_not_inspect_target_is_reported_not_silently_passed():
    trajectory = load_fixture("valid-minimal.test.json")
    trajectory["tool_calls"] = ["search_text", *trajectory["tool_calls"]]
    result = evaluate_trajectory(trajectory)
    assert result["first_tool_is_inspect_target"] is False


def test_missing_required_disposition_lowers_the_rate_below_one():
    trajectory = load_fixture("valid-minimal.test.json")
    del trajectory["required_question_dispositions"]["receiving_port"]
    result = evaluate_trajectory(trajectory)
    assert result["required_question_disposition_rate"] < 1.0


def test_unobserved_positive_evidence_is_counted_not_hidden():
    trajectory = load_fixture("valid-minimal.test.json")
    trajectory["evidence"].append({"id": "e3", "status": "confirmed", "observed": False})
    result = evaluate_trajectory(trajectory)
    assert result["ungrounded_positive_value_count"] == 1
    assert result["unobserved_evidence_count"] == 1


def test_unresolved_evidence_is_never_counted_as_ungrounded():
    trajectory = load_fixture("valid-minimal.test.json")
    trajectory["evidence"].append({"id": "e3", "status": "unresolved", "observed": False})
    result = evaluate_trajectory(trajectory)
    assert result["ungrounded_positive_value_count"] == 0


def test_recovery_without_a_fresh_observation_is_reported_false():
    trajectory = load_fixture("grounding-recovery.test.json")
    # Point the "recovery" step at the same validate_analysis call instead
    # of a real observation Tool -- a bare resubmit, not genuine recovery.
    trajectory["grounding_error_events"] = [{"tool_call_index": 2, "recovery_tool_call_index": 2}]
    result = evaluate_trajectory(trajectory)
    assert result["fresh_observation_after_grounding_error"] is False


def test_evaluator_reports_duplicate_and_no_progress_counts_without_a_fixed_threshold():
    result = evaluate_trajectory(load_fixture("valid-minimal.test.json"))
    # These must be reported as raw counts for a human/Task 7 gate to
    # interpret -- the evaluator itself must not hardcode e.g. `== 0`.
    assert result["duplicate_call_count"] == 0
    assert result["no_progress_max"] == 0
    assert "no_progress_cap" in result


def test_context_projection_leak_is_detected_when_a_value_field_appears():
    trajectory = load_fixture("valid-minimal.test.json")
    trajectory["context_projection_samples"].append({"question_id": "receiving_port", "port": 8080})
    result = evaluate_trajectory(trajectory)
    assert result["context_projection_leak_free"] is False


def test_evaluator_does_not_hardcode_a_fixed_coverage_threshold():
    """Regression guard for the plan's explicit warning against e.g.
    `question_coverage >= 4`: a trajectory covering only one required
    question out of five must still be evaluated, not rejected outright
    by the evaluator itself."""

    trajectory = load_fixture("valid-minimal.test.json")
    trajectory["required_question_dispositions"] = {"workload_deployment_unit": "confirmed"}
    result = evaluate_trajectory(trajectory)
    assert result["required_question_disposition_rate"] == pytest.approx(1 / 5)


if __name__ == "__main__":
    pytest.main([__file__])
