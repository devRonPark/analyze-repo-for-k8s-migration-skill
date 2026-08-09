from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .state import ANALYSIS_STAGES, FINAL_STAGE, PipelineState, derive_evidence_id


CLAIM_STATUSES = {"confirmed", "inferred", "unknown", "conflicted", "not_applicable"}

ALLOWED_STAGE_FIELDS = {
    "discovery": {"stage", "claims", "evidence_ids", "evidence_inputs", "rule_applications", "signals", "candidate_ids", "decisions"},
    "execution": {"stage", "claims", "evidence_ids", "evidence_inputs", "rule_applications", "discovery_fact_refs", "process_ids"},
    "relationships": {
        "stage", "claims", "evidence_ids", "evidence_inputs", "rule_applications",
        "discovery_fact_refs", "execution_fact_refs", "graph_edges", "graph_edge_ids",
    },
    "boundaries": {"stage", "claims", "evidence_ids", "evidence_inputs", "rule_applications", "discovery_fact_refs", "execution_fact_refs", "relationship_fact_refs", "workload_units", "candidate_exclusions", "unit_ids", "deployable_unit_ids", "included_candidate_ids", "excluded_candidate_ids", "decisions"},
    "contracts": {"stage", "claims", "evidence_ids", "evidence_inputs", "rule_applications", "contract_ids"},
}

ALLOWED_CLAIM_FIELDS = {"id", "status", "evidence_ids", "scope", "blocked_decision"}
ALLOWED_EVIDENCE_FIELDS = {"location", "range", "status", "content_fingerprint", "redacted"}
ALLOWED_RULE_FIELDS = {"rule_id", "evidence_ids", "process_or_candidate_ids", "decision_id"}


CONTRACT_PATH = Path(__file__).resolve().parents[3] / "contracts" / "stage-payload-contracts.json"


def _client_fields_from_contract(stage: str, fallback: set[str]) -> set[str]:
    """Use sealed client fields where a stage contract exposes them."""
    contracts = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    payload = contracts.get("stages", {}).get(stage, {}).get("client_payload")
    required = payload.get("required") if isinstance(payload, Mapping) else None
    if required is None:
        return fallback
    if not isinstance(required, list) or not required or any(not isinstance(field, str) for field in required):
        raise ValueError("invalid_stage_payload_contract")
    return set(required)


CLIENT_STAGE_FIELDS = {
    stage: _client_fields_from_contract(
        stage, (fields - {"evidence_ids", "evidence_inputs"}) | {"schema_version", "evidence"}
    )
    for stage, fields in ALLOWED_STAGE_FIELDS.items()
}
CLIENT_CLAIM_FIELDS = {"id", "status", "evidence_aliases", "scope", "blocked_decision"}
CLIENT_RULE_FIELDS = {"rule_id", "evidence_aliases", "process_or_candidate_ids", "decision_id"}
CLIENT_EVIDENCE_FIELDS = {"alias", "observation_ref"}
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")

SECRET_PATTERN = re.compile(r"password|secret|token|api[_-]?key|private[_-]?key", re.IGNORECASE)
REOPEN_REASON_PATTERN = re.compile(r"^.{3,500}$", re.DOTALL)

REOPEN_PERMITTED = {
    "discovery": set(),
    "execution": {"discovery"},
    "relationships": {"discovery", "execution"},
    "boundaries": {"discovery", "execution", "relationships"},
    "contracts": {"discovery", "execution", "relationships", "boundaries"},
    FINAL_STAGE: {"discovery", "execution", "relationships", "boundaries", "contracts"},
}


def ensure_exact_keys(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value.keys()) - allowed)
    if unknown:
        raise ValueError(f"unknown {label} field")


def ensure_known_stage(stage: str) -> None:
    if stage not in ANALYSIS_STAGES:
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
        return True
    if stage == "boundaries":
        return True
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


def _require_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"invalid {label}")
    return value


def _canonical_observation(raw: Any, binding: Mapping[str, Any]) -> dict[str, Any]:
    """Extract only server-owned canonical fields from a trusted observation."""
    if not isinstance(raw, Mapping):
        raise ValueError("invalid trusted observation")
    candidate = raw.get("canonical_evidence", raw)
    if not isinstance(candidate, Mapping):
        raise ValueError("invalid trusted observation")
    required = {"location", "range", "status", "content_fingerprint", "redacted"}
    if not required.issubset(candidate):
        raise ValueError("invalid trusted observation")
    evidence = {key: candidate[key] for key in required}
    if evidence["status"] not in CLAIM_STATUSES or evidence["redacted"] is not True:
        raise ValueError("invalid trusted observation")
    if not isinstance(evidence["location"], str) or not isinstance(evidence["range"], str) or not isinstance(evidence["content_fingerprint"], str):
        raise ValueError("invalid trusted observation")
    if SECRET_PATTERN.search(f"{evidence['location']} {evidence['content_fingerprint']}"):
        raise ValueError("secret-bearing trusted observation")
    snapshot = raw.get("snapshot_hash")
    if snapshot is not None and snapshot != binding["target_snapshot_hash"]:
        raise ValueError("trusted observation snapshot mismatch")
    return evidence


def normalize_submission_payload(
    payload: Mapping[str, Any], observations: Mapping[str, Any], binding: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Resolve ephemeral client aliases into canonical server-derived evidence.

    `observations` is process-private server data. Client input can name only an
    opaque observation reference; it cannot control evidence identity or fields.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be object")
    stage = payload.get("stage")
    ensure_known_stage(stage)
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported schema version")
    forbidden = {"evidence_ids", "evidence_inputs", "content_fingerprint", "redacted", "location"}
    if forbidden.intersection(payload):
        raise ValueError("client evidence field")
    ensure_exact_keys(payload, CLIENT_STAGE_FIELDS[stage], "client payload")
    if not isinstance(observations, Mapping):
        raise ValueError("trusted observations required")
    raw_evidence = payload.get("evidence")
    if not isinstance(raw_evidence, list):
        raise ValueError("evidence declarations required")

    alias_to_id: dict[str, str] = {}
    canonical: dict[str, dict[str, Any]] = {}
    used_refs: set[str] = set()
    for item in raw_evidence:
        if not isinstance(item, Mapping):
            raise ValueError("invalid evidence declaration")
        ensure_exact_keys(item, CLIENT_EVIDENCE_FIELDS, "evidence declaration")
        alias = _require_identifier(item.get("alias"), "evidence alias")
        ref = _require_identifier(item.get("observation_ref"), "observation reference")
        if alias in alias_to_id:
            raise ValueError("duplicate alias")
        if ref in used_refs:
            raise ValueError("duplicate observation declaration")
        if ref not in observations:
            raise ValueError("unknown observation reference")
        evidence = _canonical_observation(observations[ref], binding)
        evidence_id = derive_evidence_id({"snapshot_hash": binding["target_snapshot_hash"], **evidence})
        if evidence_id in canonical:
            raise ValueError("duplicate observation declaration")
        alias_to_id[alias] = evidence_id
        canonical[evidence_id] = evidence
        used_refs.add(ref)

    normalized_claims: list[dict[str, Any]] = []
    used_aliases: set[str] = set()
    claims = payload.get("claims", [])
    if not isinstance(claims, list):
        raise ValueError("invalid claims")
    for raw_claim in claims:
        if not isinstance(raw_claim, Mapping):
            raise ValueError("invalid claim")
        if {"evidence_ids", "evidence_inputs", "content_fingerprint", "redacted", "location"}.intersection(raw_claim):
            raise ValueError("client evidence field")
        ensure_exact_keys(raw_claim, CLIENT_CLAIM_FIELDS, "client claim")
        aliases = raw_claim.get("evidence_aliases")
        if not isinstance(aliases, list) or not aliases:
            raise ValueError("claim evidence aliases required")
        resolved_aliases = [_require_identifier(alias, "evidence alias") for alias in aliases]
        if len(resolved_aliases) != len(set(resolved_aliases)):
            raise ValueError("duplicate claim evidence alias")
        if any(alias not in alias_to_id for alias in resolved_aliases):
            raise ValueError("undeclared evidence alias")
        claim = {key: raw_claim[key] for key in ("id", "status", "scope", "blocked_decision") if key in raw_claim}
        claim["evidence_ids"] = [alias_to_id[alias] for alias in resolved_aliases]
        if claim.get("status") == "unknown" and not any(canonical[evidence_id]["status"] == "unknown" for evidence_id in claim["evidence_ids"]):
            raise ValueError("unknown claim requires absence observation")
        normalized_claims.append(claim)
        used_aliases.update(resolved_aliases)

    normalized_rules: list[dict[str, Any]] = []
    rules = payload.get("rule_applications", [])
    if not isinstance(rules, list):
        raise ValueError("invalid rule applications")
    for raw_rule in rules:
        if not isinstance(raw_rule, Mapping):
            raise ValueError("invalid rule application")
        if {"evidence_ids", "evidence_inputs", "content_fingerprint", "redacted", "location"}.intersection(raw_rule):
            raise ValueError("client evidence field")
        ensure_exact_keys(raw_rule, CLIENT_RULE_FIELDS, "client rule application")
        aliases = raw_rule.get("evidence_aliases")
        if not isinstance(aliases, list) or not aliases:
            raise ValueError("rule evidence aliases required")
        resolved_aliases = [_require_identifier(alias, "evidence alias") for alias in aliases]
        if len(resolved_aliases) != len(set(resolved_aliases)):
            raise ValueError("duplicate rule evidence alias")
        if any(alias not in alias_to_id for alias in resolved_aliases):
            raise ValueError("undeclared evidence alias")
        normalized_rules.append({
            "rule_id": raw_rule.get("rule_id"),
            "evidence_ids": [alias_to_id[alias] for alias in resolved_aliases],
            "process_or_candidate_ids": raw_rule.get("process_or_candidate_ids"),
            "decision_id": raw_rule.get("decision_id"),
        })
        used_aliases.update(resolved_aliases)

    if set(alias_to_id) != used_aliases:
        raise ValueError("unreferenced observation")
    normalized = {
        key: deepcopy(value)
        for key, value in payload.items()
        if key not in {"schema_version", "evidence", "claims", "rule_applications"}
    }
    normalized.update({
        "claims": normalized_claims,
        "evidence_ids": list(alias_to_id.values()),
        "evidence_inputs": canonical,
        "rule_applications": normalized_rules,
    })
    return normalized, canonical


def validate_claims(payload: Mapping[str, Any]) -> None:
    claims = payload.get("claims")
    if not isinstance(claims, list):
        raise ValueError("invalid claims")
    claim_ids: set[str] = set()
    for claim in claims:
        if not isinstance(claim, Mapping):
            raise ValueError("invalid claim")
        ensure_exact_keys(claim, ALLOWED_CLAIM_FIELDS, "claim")
        claim_id = _require_identifier(claim.get("id"), "claim id")
        if claim_id in claim_ids or not isinstance(claim.get("evidence_ids"), list):
            raise ValueError("invalid claim")
        claim_ids.add(claim_id)
        if claim.get("status") not in CLAIM_STATUSES:
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
    included_candidates = payload.get("included_candidate_ids", [])
    excluded_candidates = payload.get("excluded_candidate_ids", [])
    if len(included_candidates) != len(set(included_candidates)) or len(excluded_candidates) != len(set(excluded_candidates)):
        raise ValueError("duplicate boundary candidate membership")
    if set(included_candidates).intersection(excluded_candidates):
        raise ValueError("candidate cannot be both included and excluded")


def validate_finalize_state(state: PipelineState) -> None:
    if state.current_stage != FINAL_STAGE or set(state.outputs) != set(ANALYSIS_STAGES):
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
