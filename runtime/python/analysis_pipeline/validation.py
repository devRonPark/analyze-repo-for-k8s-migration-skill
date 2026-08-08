from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Mapping

from .state import STAGES, PipelineState, derive_evidence_id


CLAIM_STATUSES = {"confirmed", "inferred", "unknown", "conflicted", "not_applicable"}

ALLOWED_STAGE_FIELDS = {
    "discovery": {"stage", "claims", "evidence_ids", "evidence_inputs", "rule_applications", "signals", "candidate_ids", "decisions"},
    "execution": {"stage", "claims", "evidence_ids", "evidence_inputs", "rule_applications", "process_ids"},
    "relationships": {"stage", "claims", "evidence_ids", "evidence_inputs", "rule_applications", "graph_edge_ids"},
    "boundaries": {"stage", "claims", "evidence_ids", "evidence_inputs", "rule_applications", "unit_ids", "deployable_unit_ids", "decisions"},
    "contracts": {"stage", "claims", "evidence_ids", "evidence_inputs", "rule_applications", "contract_ids"},
    "finalize": {"stage", "claims", "evidence_ids", "evidence_inputs", "rule_applications", "decisions"},
}

ALLOWED_CLAIM_FIELDS = {"id", "status", "evidence_ids", "scope", "blocked_decision"}
ALLOWED_EVIDENCE_FIELDS = {"location", "range", "status", "content_fingerprint", "redacted"}
ALLOWED_RULE_FIELDS = {"rule_id", "evidence_ids", "process_or_candidate_ids", "decision_id"}

SECRET_PATTERN = re.compile(r"password|secret|token|api[_-]?key|private[_-]?key", re.IGNORECASE)
REOPEN_REASON_PATTERN = re.compile(r"^.{3,500}$", re.DOTALL)

REOPEN_PERMITTED = {
    "discovery": set(),
    "execution": {"discovery"},
    "relationships": {"discovery", "execution"},
    "boundaries": {"discovery", "execution", "relationships"},
    "contracts": {"discovery", "execution", "relationships", "boundaries"},
    "finalize": {"discovery", "execution", "relationships", "boundaries", "contracts"},
}


def ensure_exact_keys(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value.keys()) - allowed)
    if unknown:
        raise ValueError(f"unknown {label} field")


def ensure_known_stage(stage: str) -> None:
    if stage not in STAGES:
        raise ValueError("unknown stage")


def ensure_transition_open(state: PipelineState, expected_revision: int, expected_hash: str) -> None:
    if state.finalized:
        raise ValueError("state finalized")
    if expected_revision != state.revision or expected_hash != state.state_hash:
        raise ValueError("stale transition")
    if state.digest() != state.state_hash:
        raise ValueError("stale transition")


def ensure_finalize_ready(state: PipelineState, expected_revision: int, expected_hash: str) -> None:
    if expected_revision != state.revision or expected_hash != state.state_hash:
        raise ValueError("stale transition")
    if state.digest() != state.state_hash:
        raise ValueError("stale transition")
    if state.finalized:
        raise ValueError("state finalized")


def stage_data_present(stage: str, payload: Mapping[str, Any]) -> bool:
    if stage == "discovery":
        return bool(payload.get("signals"))
    if stage == "execution":
        return bool(payload.get("process_ids"))
    if stage == "relationships":
        return bool(payload.get("graph_edge_ids"))
    if stage == "boundaries":
        return bool(payload.get("unit_ids"))
    if stage == "contracts":
        return bool(payload.get("contract_ids"))
    return True


def validate_payload_shape(stage: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    ensure_known_stage(stage)
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be object")
    if payload.get("binding") is not None:
        raise ValueError("binding is server-owned")
    ensure_exact_keys(payload, ALLOWED_STAGE_FIELDS[stage], "payload")
    if payload.get("stage") != stage:
        raise ValueError("stage mismatch")
    if not stage_data_present(stage, payload):
        raise ValueError("stage-specific data missing")
    return deepcopy(dict(payload))


def validate_claims(payload: Mapping[str, Any]) -> None:
    for claim in payload.get("claims", []):
        if not isinstance(claim, Mapping):
            raise ValueError("invalid claim")
        ensure_exact_keys(claim, ALLOWED_CLAIM_FIELDS, "claim")
        if not claim.get("id") or not isinstance(claim.get("evidence_ids"), list):
            raise ValueError("invalid claim")
        if claim["status"] not in CLAIM_STATUSES:
            raise ValueError("invalid claim status")
        if claim["status"] == "unknown":
            if not claim.get("scope") or not claim.get("blocked_decision"):
                raise ValueError("unknown claim lacks scope/decision")
            if not claim.get("evidence_ids"):
                raise ValueError("unknown claim requires absence evidence")


def validate_evidence_inputs(payload: Mapping[str, Any], snapshot_hash: str) -> dict[str, dict[str, Any]]:
    evidence_inputs = payload.get("evidence_inputs")
    if not isinstance(evidence_inputs, Mapping):
        raise ValueError("evidence inputs required")
    normalized: dict[str, dict[str, Any]] = {}
    for evidence_id, raw_input in evidence_inputs.items():
        if not isinstance(raw_input, Mapping):
            raise ValueError("invalid evidence input")
        ensure_exact_keys(raw_input, ALLOWED_EVIDENCE_FIELDS, "evidence")
        if not evidence_id:
            raise ValueError("invalid evidence input")
        input_dict = deepcopy(dict(raw_input))
        if input_dict.get("status") not in CLAIM_STATUSES:
            raise ValueError("invalid evidence status")
        if not input_dict.get("location") or not input_dict.get("range") or not input_dict.get("content_fingerprint"):
            raise ValueError("invalid evidence input")
        if input_dict.get("redacted") is not True:
            raise ValueError("unverified evidence")
        if SECRET_PATTERN.search(f"{input_dict['location']} {input_dict['content_fingerprint']}"):
            raise ValueError("secret-bearing evidence")
        expected = derive_evidence_id({"snapshot_hash": snapshot_hash, **input_dict})
        if evidence_id != expected:
            raise ValueError("forged evidence")
        normalized[evidence_id] = input_dict
    return normalized


def validate_payload_references(payload: Mapping[str, Any]) -> None:
    evidence_ids = payload.get("evidence_ids", [])
    if not isinstance(evidence_ids, list):
        raise ValueError("evidence ids required")
    evidence_id_set = set(evidence_ids)
    if len(evidence_ids) != len(evidence_id_set):
        raise ValueError("duplicate evidence membership")
    for claim in payload.get("claims", []):
        for evidence_id in claim["evidence_ids"]:
            if evidence_id not in evidence_id_set:
                raise ValueError("evidence claim references missing evidence")
    for rule in payload.get("rule_applications", []):
        if not isinstance(rule, Mapping):
            raise ValueError("invalid rule application")
        ensure_exact_keys(rule, ALLOWED_RULE_FIELDS, "rule")
        if not rule.get("rule_id") or not rule.get("decision_id"):
            raise ValueError("invalid rule application")
        if not isinstance(rule.get("evidence_ids"), list) or not isinstance(rule.get("process_or_candidate_ids"), list):
            raise ValueError("invalid rule application")
        if not rule["evidence_ids"] or not rule["process_or_candidate_ids"]:
            raise ValueError("invalid rule application")
        for evidence_id in rule["evidence_ids"]:
            if evidence_id not in evidence_id_set:
                raise ValueError("rule evidence mismatch")
    rule_ids = [rule["rule_id"] for rule in payload.get("rule_applications", [])]
    if len(rule_ids) != len(set(rule_ids)):
        raise ValueError("duplicate rule application")


def collect_catalog_from_outputs(outputs: Mapping[str, Mapping[str, Any]]) -> dict[str, list[str]]:
    collected = {
        "process_ids": [],
        "candidate_ids": [],
        "graph_edge_ids": [],
        "unit_ids": [],
        "deployable_unit_ids": [],
        "contract_ids": [],
        "decision_ids": [],
    }
    for output in outputs.values():
        for key in ("process_ids", "candidate_ids", "graph_edge_ids", "unit_ids", "deployable_unit_ids", "contract_ids", "decisions"):
            if key in output:
                target = "decision_ids" if key == "decisions" else key
                for item in output.get(key, []):
                    if item not in collected[target]:
                        collected[target].append(item)
    return collected


def validate_rule_subjects_and_decisions(payload: Mapping[str, Any], combined_catalog: Mapping[str, list[str]]) -> None:
    valid_subjects = set(combined_catalog["process_ids"]) | set(combined_catalog["candidate_ids"])
    valid_decisions = set(combined_catalog["decision_ids"])
    for rule in payload.get("rule_applications", []):
        for subject_id in rule["process_or_candidate_ids"]:
            if subject_id not in valid_subjects:
                raise ValueError("rule subject dangling")
        if rule["decision_id"] not in valid_decisions:
            raise ValueError("rule decision dangling")


def validate_boundaries_payload(payload: Mapping[str, Any]) -> None:
    if payload.get("stage") != "boundaries":
        return
    unit_ids = payload.get("unit_ids", [])
    deployable_ids = payload.get("deployable_unit_ids", [])
    if len(unit_ids) != len(set(unit_ids)):
        raise ValueError("duplicate unit membership")
    if len(deployable_ids) != len(set(deployable_ids)):
        raise ValueError("duplicate deployable membership")
    if not set(deployable_ids).issubset(set(unit_ids)):
        raise ValueError("deployable unit must reference a known unit")


def validate_finalize_state(state: PipelineState) -> None:
    if state.current_stage != "finalize" or any(stage not in state.outputs for stage in STAGES):
        raise ValueError("pipeline is not complete")
    applications: dict[str, Mapping[str, Any]] = {}
    valid_subjects = set(state.catalog["process_ids"]) | set(state.catalog["candidate_ids"])
    valid_decisions = set(state.catalog["decision_ids"])
    for output in state.outputs.values():
        for claim in output.get("claims", []):
            if claim["status"] == "unknown" and (not claim.get("scope") or not claim.get("blocked_decision")):
                raise ValueError("unknown claim lacks scope/decision")
            for evidence_id in claim["evidence_ids"]:
                if evidence_id not in state.evidence:
                    raise ValueError("dangling evidence")
        for rule in output.get("rule_applications", []):
            if rule["rule_id"] in applications:
                raise ValueError("duplicate rule application")
            applications[rule["rule_id"]] = rule
            if any(evidence_id not in state.evidence for evidence_id in rule["evidence_ids"]):
                raise ValueError("rule evidence dangling")
            if any(subject_id not in valid_subjects for subject_id in rule["process_or_candidate_ids"]):
                raise ValueError("rule subject dangling")
            if rule["decision_id"] not in valid_decisions:
                raise ValueError("rule decision dangling")
    for rule_id in state.binding["required_rule_ids"]:
        if rule_id not in applications:
            raise ValueError("mandatory rule unapplied")
