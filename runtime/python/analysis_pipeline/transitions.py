from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

from .state import ANALYSIS_STAGES, FINAL_STAGE, PipelineState, with_hash
from .validation import (
    REOPEN_PERMITTED,
    collect_catalog_from_outputs,
    ensure_finalize_ready,
    ensure_transition_open,
    validate_boundaries_payload,
    validate_evidence_inputs,
    validate_finalize_state,
    validate_payload_references,
    validate_payload_shape,
    validate_claims,
    validate_rule_subjects_and_decisions,
)


def _next_stage(stage: str) -> str:
    index = ANALYSIS_STAGES.index(stage)
    return ANALYSIS_STAGES[index + 1] if index + 1 < len(ANALYSIS_STAGES) else FINAL_STAGE


def _combined_catalog(state: PipelineState, payload: dict[str, Any]) -> dict[str, list[str]]:
    outputs = {**state.outputs, payload["stage"]: payload}
    return collect_catalog_from_outputs(outputs)


def _append_evidence(state: PipelineState, stage: str, payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    evidence = deepcopy(state.evidence)
    evidence_inputs = validate_evidence_inputs(payload, state.binding["target_snapshot_hash"])
    for evidence_id in payload["evidence_ids"]:
        if evidence_id not in evidence_inputs:
            raise ValueError("unverified evidence")
        candidate = {"stage": stage, **evidence_inputs[evidence_id]}
        if evidence_id in evidence:
            # A later vertical slice may re-ground the same immutable, redacted
            # observation. The ID is bound to its canonical evidence, so reuse
            # it rather than letting the caller manufacture a distinct record.
            existing = evidence[evidence_id]
            if {key: value for key, value in existing.items() if key != "stage"} != {
                key: value for key, value in candidate.items() if key != "stage"
            }:
                raise ValueError("evidence collision")
            continue
        evidence[evidence_id] = candidate
    return evidence


def submit(state: PipelineState, stage: str, payload: dict[str, Any], expected_revision: int, expected_hash: str) -> PipelineState:
    ensure_transition_open(state, expected_revision, expected_hash)
    if state.current_stage != stage:
        raise ValueError("stage order")
    if stage in state.outputs:
        raise ValueError("duplicate stage submission")
    payload = validate_payload_shape(stage, payload)
    validate_claims(payload)
    validate_payload_references(payload)
    validate_boundaries_payload(payload)
    evidence = _append_evidence(state, stage, payload)
    catalog = _combined_catalog(state, payload)
    validate_rule_subjects_and_decisions(payload, catalog)
    next_state = replace(
        state,
        revision=state.revision + 1,
        current_stage=_next_stage(stage),
        outputs={**state.outputs, stage: payload},
        evidence=evidence,
        catalog=catalog,
    )
    return with_hash(next_state)


def reopen(state: PipelineState, target_stage: str, reason: str, expected_revision: int, expected_hash: str) -> PipelineState:
    ensure_transition_open(state, expected_revision, expected_hash)
    if target_stage not in ANALYSIS_STAGES:
        raise ValueError("invalid reopen target")
    if target_stage not in REOPEN_PERMITTED[state.current_stage]:
        raise ValueError("invalid back-edge")
    if not isinstance(reason, str) or reason.strip() != reason or len(reason) < 3 or len(reason) > 500:
        raise ValueError("invalid reopen reason")

    kept_outputs = {
        stage_name: deepcopy(output)
        for stage_name, output in state.outputs.items()
        if ANALYSIS_STAGES.index(stage_name) < ANALYSIS_STAGES.index(target_stage)
    }
    kept_evidence = {
        evidence_id: deepcopy(item)
        for evidence_id, item in state.evidence.items()
        if ANALYSIS_STAGES.index(item["stage"]) < ANALYSIS_STAGES.index(target_stage)
    }
    next_state = replace(
        state,
        revision=state.revision + 1,
        current_stage=target_stage,
        finalized=False,
        outputs=kept_outputs,
        evidence=kept_evidence,
        catalog=collect_catalog_from_outputs(kept_outputs),
        reopen_reasons=state.reopen_reasons + (reason,),
    )
    return with_hash(next_state)


def finalize(state: PipelineState, expected_revision: int, expected_hash: str) -> PipelineState:
    ensure_finalize_ready(state, expected_revision, expected_hash)
    validate_finalize_state(state)
    return with_hash(replace(state, revision=state.revision + 1, finalized=True))
