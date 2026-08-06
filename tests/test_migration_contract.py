"""Lock the Kubernetes migration exploration contract before any orchestration code exists.

This module is the executable specification for Task 0 of
docs/superpowers/plans/2026-08-06-kubernetes-migration-agent-lesson-learned-and-improvement-plan.md.
It fixes, as deterministic tests, the question-disposition truth table, the
AnalysisResult/run_metadata boundary, the allowed `exploration_signals`
fields, and the bounded stop-gate rules that later tasks (exploration_policy,
exploration_ledger, exploration_context) must satisfy. Nothing here reaches
into a live model, a live repository, or the network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from migration_assistant.analysis import AnalysisResult
from migration_assistant.tool_contract import PUBLIC_AGENT_TOOL_NAMES

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "adk_migration_contract"

IMPORTANCE_LEVELS = {"required", "conditional", "optional"}
QUESTION_STATUS_VALUES = {"confirmed", "inferred", "unresolved", "conflicting", "not_applicable"}

# The domain fields AnalysisResult is allowed to carry. Any run-execution
# telemetry (Tool trajectory, callback counters, recovery/budget counters)
# must live in run_metadata instead -- never in this set.
ANALYSIS_RESULT_DOMAIN_FIELDS = {
    "status", "summary", "evidence", "findings", "components", "iterations", "errors", "termination",
}

# The telemetry keys migration_assistant.analysis.analyze() currently writes
# into run_metadata. Locked here so a future change cannot silently promote
# one of these into the AnalysisResult domain schema.
RUN_METADATA_TELEMETRY_FIELDS = {
    "terminal", "tool_calls", "protocol_issues", "callback_telemetry", "recovery_attempts",
    "run_control", "evidence_provenance", "provenance_summary",
}

ALLOWED_EXPLORATION_SIGNAL_FIELDS = {
    "question_id", "trigger_rule_id", "observed_fact_ref", "candidate_observation_kind",
}

# Tokens that would turn an advisory signal into a conclusion, a final
# status, or a forced next Tool call -- all forbidden regardless of which
# allowed field carries them.
FORBIDDEN_EXPLORATION_SIGNAL_VALUE_TOKENS = {
    "deployment", "confirmed", "inferred", "unresolved", "conflicting", "not_applicable",
    "read_file", "read_file_lines", "search_text", "list_tree", "find_files",
    "inspect_target", "inspect_git_metadata", "validate_analysis",
}


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def resolve_question_disposition(case: Mapping[str, Any]) -> str:
    """Reference oracle for the Task 0 question-disposition truth table.

    Returns one of QUESTION_STATUS_VALUES, or "rejected" when the model's
    claim is not backed by a ledger record and therefore cannot be accepted.
    """

    ledger = case.get("ledger", {})
    if ledger.get("conflicting_positive"):
        return "conflicting"
    if ledger.get("precondition_observed") is False:
        return "not_applicable"
    if ledger.get("positive_evidence_count", 0) > 0:
        return "inferred" if ledger.get("inferred_only") else "confirmed"
    if case.get("model_claim") == "unresolved":
        has_scope = bool(ledger.get("search_scope"))
        has_pattern = bool(ledger.get("search_pattern"))
        has_count = isinstance(ledger.get("observation_count"), int) and ledger.get("observation_count") >= 0
        if has_scope and has_pattern and has_count:
            return "unresolved"
    return "rejected"


def evaluate_stop_gate(case_input: Mapping[str, Any]) -> dict[str, Any]:
    """Reference oracle for the Task 0 bounded stop-gate truth table."""

    evidence_count = case_input["evidence_count"]
    positive_without_evidence = bool(case_input.get("positive_without_evidence", False))
    bounded_stop_triggered = bool(case_input.get("bounded_stop_triggered", False))
    required = dict(case_input.get("required_question_dispositions", {}))

    invalid = set(required.values()) - QUESTION_STATUS_VALUES
    if invalid:
        raise ValueError(f"알 수 없는 질문 상태입니다: {sorted(invalid)}")

    if evidence_count == 0:
        return {"submit_allowed": False, "allowed_status": set(), "reason": "no_evidence"}
    if positive_without_evidence:
        return {"submit_allowed": False, "allowed_status": set(), "reason": "ungrounded_positive_value"}
    if bounded_stop_triggered:
        return {"submit_allowed": True, "allowed_status": {"failed", "partial"}, "reason": "bounded_stop"}
    if "conflicting" in required.values():
        return {"submit_allowed": True, "allowed_status": {"partial"}, "reason": "conflicting_no_auto_select"}
    if "unresolved" in required.values():
        return {"submit_allowed": True, "allowed_status": {"partial"}, "reason": "genuine_unresolved"}
    if "not_applicable" in required.values():
        return {"submit_allowed": True, "allowed_status": {"partial"}, "reason": "not_applicable_precondition"}
    return {"submit_allowed": True, "allowed_status": {"complete", "partial"}, "reason": "confirmed_or_inferred"}


def validate_exploration_signal(signal: Mapping[str, Any]) -> None:
    """Raise ValueError if `signal` is not a bare advisory-hint envelope."""

    extra = set(signal) - ALLOWED_EXPLORATION_SIGNAL_FIELDS
    if extra:
        raise ValueError(f"exploration_signal에 허용되지 않은 필드가 있습니다: {sorted(extra)}")
    for value in signal.values():
        if isinstance(value, str) and value.strip().casefold() in FORBIDDEN_EXPLORATION_SIGNAL_VALUE_TOKENS:
            raise ValueError(f"exploration_signal 값에 결론/상태/Tool 호출 토큰이 포함됐습니다: {value}")


# ---------------------------------------------------------------------------
# Section A: question importance and disposition status
# ---------------------------------------------------------------------------


def test_question_importance_levels_are_fixed():
    fixture = load_fixture("question-dispositions.json")
    assert set(fixture["importance_levels"]) == IMPORTANCE_LEVELS
    for question in fixture["questions"]:
        assert question["importance"] in IMPORTANCE_LEVELS


def test_question_status_values_are_fixed():
    fixture = load_fixture("question-dispositions.json")
    assert set(fixture["status_values"]) == QUESTION_STATUS_VALUES


@pytest.mark.parametrize("case", load_fixture("question-dispositions.json")["disposition_cases"], ids=lambda case: case["case_id"])
def test_disposition_cases_match_oracle(case):
    assert resolve_question_disposition(case) == case["expected_status"]


def test_model_claim_alone_cannot_produce_unresolved():
    case = {"question_id": "production_startup", "model_claim": "unresolved", "ledger": {}}
    assert resolve_question_disposition(case) == "rejected"


def test_unresolved_requires_scope_pattern_and_observation_count():
    complete_ledger = {
        "positive_evidence_count": 0,
        "search_scope": "Dockerfile*",
        "search_pattern": "ENTRYPOINT|CMD",
        "observation_count": 1,
    }
    case = {"question_id": "production_startup", "model_claim": "unresolved", "ledger": complete_ledger}
    assert resolve_question_disposition(case) == "unresolved"

    for missing_key in ("search_scope", "search_pattern", "observation_count"):
        incomplete_ledger = dict(complete_ledger)
        del incomplete_ledger[missing_key]
        incomplete_case = {"question_id": "production_startup", "model_claim": "unresolved", "ledger": incomplete_ledger}
        assert resolve_question_disposition(incomplete_case) == "rejected"


# ---------------------------------------------------------------------------
# Section B: AnalysisResult and run_metadata must never mix
# ---------------------------------------------------------------------------


def test_analysis_result_schema_is_exactly_the_domain_fields():
    assert set(AnalysisResult.model_fields) == ANALYSIS_RESULT_DOMAIN_FIELDS


def test_analysis_result_domain_fields_never_overlap_run_metadata_telemetry():
    assert ANALYSIS_RESULT_DOMAIN_FIELDS.isdisjoint(RUN_METADATA_TELEMETRY_FIELDS)


def test_analysis_result_rejects_run_telemetry_keys_as_extra_fields():
    with pytest.raises(ValueError):
        AnalysisResult.model_validate(
            {
                "status": "partial",
                "summary": "s",
                "evidence": [],
                "errors": ["x"],
                "tool_calls": ["read_file"],
            }
        )


# ---------------------------------------------------------------------------
# Section C: exploration_signals allowed/forbidden field contract
# ---------------------------------------------------------------------------


def test_exploration_signal_allows_only_the_four_contract_fields():
    signal = {
        "question_id": "production_startup",
        "trigger_rule_id": "container_or_process_descriptor",
        "observed_fact_ref": "observation-17",
        "candidate_observation_kind": "container_entrypoint_hit",
    }
    validate_exploration_signal(signal)  # must not raise


@pytest.mark.parametrize(
    "forbidden_key,forbidden_value",
    [
        ("workload", "Deployment"),
        ("status", "confirmed"),
        ("next_tool", "read_file"),
        ("port", "8080"),
        ("value", "solar-pro3"),
    ],
)
def test_exploration_signal_rejects_fields_outside_the_contract(forbidden_key, forbidden_value):
    signal = {"question_id": "production_startup", forbidden_key: forbidden_value}
    with pytest.raises(ValueError):
        validate_exploration_signal(signal)


@pytest.mark.parametrize(
    "field_name,conclusion_value",
    [
        ("candidate_observation_kind", "confirmed"),
        ("candidate_observation_kind", "read_file"),
        ("trigger_rule_id", "unresolved"),
    ],
)
def test_exploration_signal_rejects_conclusion_tokens_even_in_allowed_fields(field_name, conclusion_value):
    signal = {"question_id": "production_startup", field_name: conclusion_value}
    with pytest.raises(ValueError):
        validate_exploration_signal(signal)


def test_forbidden_exploration_signal_tokens_do_not_collide_with_allowed_fields():
    assert ALLOWED_EXPLORATION_SIGNAL_FIELDS.isdisjoint(FORBIDDEN_EXPLORATION_SIGNAL_VALUE_TOKENS)


# ---------------------------------------------------------------------------
# Section D: bounded stop-gate truth table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", load_fixture("stop-gate-cases.json")["cases"], ids=lambda case: case["case_id"])
def test_stop_gate_cases_match_oracle(case):
    result = evaluate_stop_gate(case["input"])
    expected = case["expected"]
    assert result["submit_allowed"] == expected["submit_allowed"]
    assert result["allowed_status"] == set(expected["allowed_status"])
    assert result["reason"] == expected["reason"]


def test_zero_evidence_blocks_submission():
    result = evaluate_stop_gate({
        "evidence_count": 0,
        "positive_without_evidence": False,
        "bounded_stop_triggered": False,
        "required_question_dispositions": {"workload_deployment_unit": "confirmed"},
    })
    assert result["submit_allowed"] is False


def test_positive_value_without_evidence_blocks_submission():
    result = evaluate_stop_gate({
        "evidence_count": 2,
        "positive_without_evidence": True,
        "bounded_stop_triggered": False,
        "required_question_dispositions": {},
    })
    assert result["submit_allowed"] is False


def test_duplicate_no_progress_or_budget_exhaustion_is_a_bounded_stop():
    result = evaluate_stop_gate({
        "evidence_count": 1,
        "positive_without_evidence": False,
        "bounded_stop_triggered": True,
        "required_question_dispositions": {},
    })
    assert result["submit_allowed"] is True
    assert result["allowed_status"] <= {"failed", "partial"}


def test_conflicting_required_disposition_never_auto_selects_one_value():
    result = evaluate_stop_gate({
        "evidence_count": 2,
        "positive_without_evidence": False,
        "bounded_stop_triggered": False,
        "required_question_dispositions": {"receiving_port": "conflicting"},
    })
    assert result["submit_allowed"] is True
    assert result["allowed_status"] == {"partial"}


# ---------------------------------------------------------------------------
# Section E: public Agent Tool surface stays at exactly eight tools
# ---------------------------------------------------------------------------


def test_public_agent_tool_surface_is_exactly_eight_read_only_tools():
    assert PUBLIC_AGENT_TOOL_NAMES == (
        "inspect_target",
        "list_tree",
        "find_files",
        "search_text",
        "read_file",
        "read_file_lines",
        "inspect_git_metadata",
        "validate_analysis",
    )
    assert "record_evidence" not in PUBLIC_AGENT_TOOL_NAMES
