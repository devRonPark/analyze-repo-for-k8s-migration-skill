"""Narrow D08 recovery for proven Boundaries correction nonconvergence.

This module deliberately has no stage registry or provider behaviour.  It
recognizes only the Boundaries decision fields and builds a separate payload
from server-owned predecessor state plus already-issued scoped absences.
"""
from __future__ import annotations

import hashlib
from typing import Any, Mapping

from .state import canonical_json


BOUNDARIES_NONCONVERGENCE_THRESHOLD = 4
_ABSENCE_CATEGORIES = {
    "lifecycle": "lifecycle signals",
    "state": "persistent writable locations",
}
_START_CATEGORY = "independent start definitions"


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _canonical(value: Any) -> Any:
    """Ignore ordering noise in the set-like Boundaries decision structures."""
    if isinstance(value, Mapping):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        normalized = [_canonical(item) for item in value]
        return sorted(normalized, key=canonical_json)
    return value


def _error_path(code: str, issue: str) -> str | None:
    text = f"{code} {issue}".lower()
    if "workload" in text or "boundary field" in text:
        return "payload.workload_units"
    if "candidate exclusion" in text or "candidate disposition" in text:
        return "payload.candidate_exclusions"
    if "claim" in text:
        return "payload.claims"
    if "evidence" in text or "observation" in text or "alias" in text:
        return "payload.evidence"
    if "rule" in text:
        return "payload.rule_applications"
    if "missing boundaries payload field" in text or "unknown boundaries payload field" in text:
        return "payload.boundaries_shape"
    return None


def _relevant_projection(payload: Mapping[str, Any], path: str) -> Any:
    if path == "payload.workload_units":
        return _canonical(payload.get("workload_units"))
    if path == "payload.candidate_exclusions":
        return _canonical(payload.get("candidate_exclusions"))
    if path == "payload.claims":
        return _canonical(payload.get("claims"))
    if path == "payload.evidence":
        return _canonical(payload.get("evidence"))
    if path == "payload.rule_applications":
        return _canonical(payload.get("rule_applications"))
    if path == "payload.boundaries_shape":
        return _canonical({
            key: payload.get(key)
            for key in (
                "evidence", "claims", "rule_applications", "discovery_fact_refs",
                "execution_fact_refs", "relationship_fact_refs", "workload_units",
                "candidate_exclusions",
            )
        })
    raise ValueError("unsupported boundaries recovery path")


def _decision_projection(payload: Mapping[str, Any]) -> Any:
    # This is intentionally narrower than the complete wire payload.  It
    # covers the two Boundary classification structures; claim/evidence alias
    # ordering and unrelated envelope fields cannot disguise a blind loop.
    return _canonical({
        "workload_units": payload.get("workload_units"),
        "candidate_exclusions": payload.get("candidate_exclusions"),
    })


def observe_boundaries_rejection(payload: Any, result: Mapping[str, Any], previous: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Return compact server-only rejection evidence, never the payload itself."""
    if not isinstance(payload, Mapping):
        return None
    code = result.get("code")
    issues = result.get("issues")
    if not isinstance(code, str) or not isinstance(issues, list) or len(issues) != 1 or not isinstance(issues[0], str):
        return None
    path = _error_path(code, issues[0])
    if path is None:
        return None
    relevant_fingerprint = _fingerprint(_relevant_projection(payload, path))
    decision_fingerprint = _fingerprint(_decision_projection(payload))
    return {
        "stage": "boundaries",
        "attempt": (int(previous["attempt"]) + 1) if previous is not None else 1,
        "error_code": code,
        "error_path": path,
        "actionable": True,
        "relevant_fingerprint": relevant_fingerprint,
        "decision_fingerprint": decision_fingerprint,
        "relevant_changed": previous is not None and decision_fingerprint != previous["decision_fingerprint"],
    }


def detect_boundaries_nonconvergence(history: list[Mapping[str, Any]]) -> str | None:
    """Classify the final bounded sequence as R1, R2, or not yet proven.

    R1 needs the same error code/path and unchanged path-local projection.
    R2 needs four actionable rejections whose normalized Boundary decision
    projection changes on every correction opportunity.  Neither condition is
    a retry count alone.
    """
    if len(history) < BOUNDARIES_NONCONVERGENCE_THRESHOLD:
        return None
    window = history[-BOUNDARIES_NONCONVERGENCE_THRESHOLD:]
    if not all(entry.get("stage") == "boundaries" and entry.get("actionable") is True for entry in window):
        return None
    first = window[0]
    if all(
        entry.get("error_code") == first.get("error_code")
        and entry.get("error_path") == first.get("error_path")
        and entry.get("relevant_fingerprint") == first.get("relevant_fingerprint")
        for entry in window[1:]
    ):
        return "R1"
    decision_paths = {"payload.workload_units", "payload.candidate_exclusions"}
    if (
        all(entry.get("error_path") in decision_paths for entry in window)
        and all(entry.get("decision_fingerprint") != prior.get("decision_fingerprint") for prior, entry in zip(window, window[1:]))
    ):
        return "R2"
    return None


def recover_boundaries_payload(
    *, registry: Any, snapshot: Any, binding: Mapping[str, Any], survey: list[Mapping[str, Any]],
    discovery_fact_refs: list[str], execution_fact_refs: list[str], relationship_fact_refs: list[str],
    process_ids: list[str], candidate_ids: list[str], validate: Any,
) -> dict[str, Any]:
    """Create the sole D08 degraded payload from already trusted inputs.

    A single accepted runtime process makes grouping deterministic. Its start
    condition can use only the matching server survey observation; every
    decision not established by that observation stays explicitly unknown and
    is tied to a pre-issued scoped absence.
    """
    if len(process_ids) != 1:
        raise ValueError("degraded Boundaries recovery requires exactly one accepted process")
    by_category = {
        item.get("category"): item.get("observation_ref")
        for item in survey
        if isinstance(item, Mapping) and item.get("status") == "unknown" and isinstance(item.get("observation_ref"), str)
    }
    start = next(
        (item for item in survey if isinstance(item, Mapping) and item.get("category") == _START_CATEGORY
         and item.get("status") in {"confirmed", "unknown"} and isinstance(item.get("observation_ref"), str)),
        None,
    )
    if start is None or any(category not in by_category for category in _ABSENCE_CATEGORIES.values()):
        raise ValueError("degraded Boundaries recovery lacks required scoped-absence observations")
    aliases = {
        "start": start["observation_ref"],
        "lifecycle": by_category[_ABSENCE_CATEGORIES["lifecycle"]],
        "state": by_category[_ABSENCE_CATEGORIES["state"]],
    }
    evidence = [{"alias": alias, "observation_ref": ref} for alias, ref in aliases.items()]
    claims = []
    start_status = "confirmed" if start["status"] == "confirmed" else "unknown"
    # The Boundary itself remains unknown because the lifecycle survey is a
    # scoped absence. The same claim also consumes the start observation, so a
    # positive start condition is never introduced without server evidence.
    claims.append({
        "id": "recovery-unit-1-boundary", "status": "unknown", "evidence_aliases": ["start", "lifecycle"],
        "scope": "boundaries survey", "blocked_decision": "workload_boundary",
    })
    for suffix, alias, decision in (
        ("lifecycle", "lifecycle", "workload_lifecycle"),
        ("state", "state", "workload_state"),
        ("deployability", "lifecycle", "workload_deployability"),
    ):
        claims.append({
            "id": f"recovery-unit-1-{suffix}", "status": "unknown", "evidence_aliases": [alias],
            "scope": "boundaries survey", "blocked_decision": decision,
        })
    exclusions = []
    for index, candidate_id in enumerate(candidate_ids, 1):
        claim_id = f"recovery-candidate-{index}"
        claims.append({
            "id": claim_id, "status": "unknown", "evidence_aliases": ["lifecycle"],
            "scope": "boundaries survey", "blocked_decision": "candidate_deployment_eligibility",
        })
        exclusions.append({"candidate_id": candidate_id, "disposition": "unknown", "claim_ids": [claim_id]})
    payload = {
        "schema_version": 1,
        "stage": "boundaries",
        "evidence": evidence,
        "claims": claims,
        "rule_applications": [],
        "discovery_fact_refs": discovery_fact_refs,
        "execution_fact_refs": execution_fact_refs,
        "relationship_fact_refs": relationship_fact_refs,
        "workload_units": [{
            "id": "recovery-unit-1", "process_ids": list(process_ids), "candidate_ids": [],
            "start_definition_status": start_status, "independent_lifecycle_status": "unknown",
            "boundary_status": "unknown", "lifecycle": "unknown", "state_decision": "unknown",
            "deployable": False, "deployability_status": "unknown",
            "boundary_claim_ids": ["recovery-unit-1-boundary"],
            "lifecycle_claim_ids": ["recovery-unit-1-lifecycle"],
            "state_claim_ids": ["recovery-unit-1-state"],
            "deployability_claim_ids": ["recovery-unit-1-deployability"],
        }],
        "candidate_exclusions": exclusions,
    }
    return validate(
        payload, registry, snapshot, binding, discovery_fact_refs, execution_fact_refs,
        relationship_fact_refs, process_ids, candidate_ids,
    )
