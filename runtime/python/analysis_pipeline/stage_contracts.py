"""Load the single stage-payload contract source of truth."""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Mapping

from .observations import ObservationRegistry, TargetSnapshot
from .state import PipelineState
from .transitions import submit
from .validation import CLAIM_STATUSES, ensure_exact_keys, normalize_submission_payload

CONTRACT_PATH = Path(__file__).resolve().parents[3] / "contracts" / "stage-payload-contracts.json"


def load_contracts(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def stage_contract(stage: str, path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contracts = load_contracts(path)
    try:
        return contracts["stages"][stage]
    except KeyError as exc:
        raise ValueError("unknown_stage_contract") from exc


def client_payload_required_fields(stage: str) -> set[str]:
    """Read the required client fields from the sealed stage contract."""
    payload = stage_contract(stage).get("client_payload")
    required = payload.get("required") if isinstance(payload, Mapping) else None
    if not isinstance(required, list) or not required or any(not isinstance(field, str) for field in required):
        raise ValueError("invalid_stage_payload_contract")
    return set(required)


def relationship_edge_contract() -> dict[str, Any]:
    """Return the executable Relationships edge fragment from the sealed contract."""
    payload = stage_contract("relationships").get("client_payload")
    edges = payload.get("graph_edges") if isinstance(payload, Mapping) else None
    if not isinstance(edges, Mapping) or not edges or any(not isinstance(key, str) for key in edges):
        raise ValueError("invalid_relationship_edge_contract")
    return dict(edges)


def workload_unit_contract() -> dict[str, Any]:
    payload = stage_contract("boundaries").get("client_payload")
    units = payload.get("workload_units") if isinstance(payload, Mapping) else None
    if not isinstance(units, Mapping) or not units:
        raise ValueError("invalid_workload_unit_contract")
    return dict(units)


def candidate_exclusion_contract() -> dict[str, Any]:
    payload = stage_contract("boundaries").get("client_payload")
    exclusions = payload.get("candidate_exclusions") if isinstance(payload, Mapping) else None
    if not isinstance(exclusions, Mapping) or not exclusions:
        raise ValueError("invalid_candidate_exclusion_contract")
    return dict(exclusions)


def _require_contract_fields(stage: str, payload: Mapping[str, Any]) -> None:
    required = client_payload_required_fields(stage)
    if missing := required.difference(payload):
        raise ValueError(f"missing {stage} payload field")
    if unexpected := set(payload).difference(required):
        raise ValueError(f"unknown {stage} payload field")


_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")


def _require_identifier_list(payload: Mapping[str, Any], field: str, *, allow_empty: bool = True) -> None:
    values = payload.get(field)
    if not isinstance(values, list) or (not allow_empty and not values):
        raise ValueError(f"invalid {field}")
    if len(values) != len(set(values)) or any(not isinstance(value, str) or not _IDENTIFIER.fullmatch(value) for value in values):
        raise ValueError(f"invalid {field}")


def validate_discovery_payload(
    payload: Mapping[str, Any],
    registry: ObservationRegistry,
    snapshot: TargetSnapshot,
    binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Resolve Discovery aliases strictly to process-private observations."""
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be object")
    _require_contract_fields("discovery", payload)
    raw_evidence = payload.get("evidence")
    if not isinstance(raw_evidence, list) or not raw_evidence:
        raise ValueError("discovery requires trusted evidence")
    raw_claims = payload.get("claims")
    if not isinstance(raw_claims, list) or not raw_claims:
        raise ValueError("discovery requires grounded claims")
    observations: dict[str, dict[str, Any]] = {}
    if isinstance(raw_evidence, list):
        for item in raw_evidence:
            if isinstance(item, Mapping) and isinstance(item.get("observation_ref"), str):
                reference = item["observation_ref"]
                observations[reference] = registry.resolve(reference, "discovery", snapshot)
    normalized, _ = normalize_submission_payload(payload, observations, binding)
    for field, allow_empty in (("signals", False), ("candidate_ids", True), ("decisions", True)):
        _require_identifier_list(normalized, field, allow_empty=allow_empty)
    return normalized


def promote_discovery_facts(state: PipelineState, payload: Mapping[str, Any]) -> PipelineState:
    """Atomically promote a validated Discovery payload into trusted state."""
    return submit(state, "discovery", dict(payload), state.revision, state.state_hash)


def project_discovery_handoff(state: PipelineState) -> dict[str, list[str]]:
    """Expose only stable identifiers, never client or repository evidence."""
    payload = state.outputs.get("discovery")
    if not isinstance(payload, Mapping):
        raise ValueError("discovery output is unavailable")
    claims = payload.get("claims")
    if not isinstance(claims, list):
        raise ValueError("discovery claims are unavailable")
    fact_refs = [f"fact_discovery_{claim['id']}" for claim in claims if isinstance(claim, Mapping) and claim.get("status") != "unknown"]
    unknown_ids = [claim["id"] for claim in claims if isinstance(claim, Mapping) and claim.get("status") == "unknown"]
    return {
        "candidate_ids": list(payload.get("candidate_ids", [])),
        "discovery_fact_refs": fact_refs,
        "unknown_ids": unknown_ids,
    }


def validate_execution_payload(
    payload: Mapping[str, Any],
    registry: ObservationRegistry,
    snapshot: TargetSnapshot,
    binding: Mapping[str, Any],
    discovery_fact_refs: list[str],
) -> dict[str, Any]:
    """Resolve Execution evidence and consume exactly the trusted discovery facts."""
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be object")
    _require_contract_fields("execution", payload)
    raw_evidence = payload.get("evidence")
    if not isinstance(raw_evidence, list) or not raw_evidence:
        raise ValueError("execution requires trusted evidence")
    raw_claims = payload.get("claims")
    if not isinstance(raw_claims, list) or not raw_claims:
        raise ValueError("execution requires grounded claims")
    observations: dict[str, dict[str, Any]] = {}
    for item in raw_evidence:
        if isinstance(item, Mapping) and isinstance(item.get("observation_ref"), str):
            reference = item["observation_ref"]
            observations[reference] = registry.resolve(reference, "execution", snapshot)
    normalized, _ = normalize_submission_payload(payload, observations, binding)
    submitted_refs = normalized.get("discovery_fact_refs")
    _require_identifier_list(normalized, "process_ids")
    if not isinstance(submitted_refs, list) or submitted_refs != discovery_fact_refs:
        raise ValueError("unknown discovery fact reference")
    return normalized


def promote_execution_facts(state: PipelineState, payload: Mapping[str, Any]) -> PipelineState:
    """Atomically promote a validated Execution payload into trusted state."""
    return submit(state, "execution", dict(payload), state.revision, state.state_hash)


def project_execution_handoff(state: PipelineState) -> dict[str, list[str]]:
    """Expose only trusted execution identifiers to the current successor."""
    payload = state.outputs.get("execution")
    if not isinstance(payload, Mapping):
        raise ValueError("execution output is unavailable")
    claims = payload.get("claims")
    if not isinstance(claims, list):
        raise ValueError("execution claims are unavailable")
    return {
        "process_ids": list(payload.get("process_ids", [])),
        "execution_fact_refs": [
            f"fact_execution_{claim['id']}"
            for claim in claims
            if isinstance(claim, Mapping) and claim.get("status") != "unknown"
        ],
        "unknown_ids": [
            claim["id"]
            for claim in claims
            if isinstance(claim, Mapping) and claim.get("status") == "unknown"
        ],
    }


def validate_relationships_payload(
    payload: Mapping[str, Any],
    registry: ObservationRegistry,
    snapshot: TargetSnapshot,
    binding: Mapping[str, Any],
    discovery_fact_refs: list[str],
    execution_fact_refs: list[str],
    process_ids: list[str],
) -> dict[str, Any]:
    """Resolve Relationships evidence and consume exactly trusted predecessor facts."""
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be object")
    _require_contract_fields("relationships", payload)
    raw_evidence = payload.get("evidence")
    if not isinstance(raw_evidence, list) or not raw_evidence:
        raise ValueError("relationships requires trusted evidence")
    raw_claims = payload.get("claims")
    if not isinstance(raw_claims, list) or not raw_claims:
        raise ValueError("relationships requires grounded claims")
    observations: dict[str, dict[str, Any]] = {}
    for item in raw_evidence:
        if isinstance(item, Mapping) and isinstance(item.get("observation_ref"), str):
            reference = item["observation_ref"]
            observations[reference] = registry.resolve(reference, "relationships", snapshot)
    normalized, _ = normalize_submission_payload(payload, observations, binding)
    normalized["graph_edge_ids"] = _validate_relationship_edges(
        normalized.get("graph_edges"), normalized.get("claims"), process_ids
    )
    submitted_discovery = normalized.get("discovery_fact_refs")
    if not isinstance(submitted_discovery, list) or submitted_discovery != discovery_fact_refs:
        raise ValueError("unknown discovery fact reference")
    submitted_execution = normalized.get("execution_fact_refs")
    if not isinstance(submitted_execution, list) or submitted_execution != execution_fact_refs:
        raise ValueError("unknown execution fact reference")
    return normalized


def _edge_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid relationship {label}")
    return value


def _edge_enum(edge_contract: Mapping[str, Any], field: str) -> set[str]:
    raw = edge_contract.get(field)
    if not isinstance(raw, str) or "|" not in raw:
        raise ValueError("invalid_relationship_edge_contract")
    values = set(raw.split("|"))
    if not values or any(not _IDENTIFIER.fullmatch(value) for value in values):
        raise ValueError("invalid_relationship_edge_contract")
    return values


def _validate_relationship_edges(raw_edges: Any, claims: Any, process_ids: list[str]) -> list[str]:
    """Validate edge topology and retain only safe identifiers in the handoff."""
    if not isinstance(raw_edges, list):
        raise ValueError("invalid graph edges")
    if not isinstance(claims, list):
        raise ValueError("relationships claims are unavailable")
    claims_by_id: dict[str, str] = {}
    for claim in claims:
        if not isinstance(claim, Mapping):
            raise ValueError("invalid relationship claim")
        claim_id = _edge_identifier(claim.get("id"), "claim id")
        status = claim.get("status")
        if status not in CLAIM_STATUSES or claim_id in claims_by_id:
            raise ValueError("invalid relationship claim")
        claims_by_id[claim_id] = status
    if len(claims_by_id) != len(claims):
        raise ValueError("invalid relationship claim")
    edge_contract = relationship_edge_contract()
    edge_fields = set(edge_contract)
    target_kinds = _edge_enum(edge_contract, "target_kind")
    dependency_types = _edge_enum(edge_contract, "dependency_type")
    edge_statuses = _edge_enum(edge_contract, "status")
    required_statuses = _edge_enum(edge_contract, "required_for_function")
    startup_statuses = _edge_enum(edge_contract, "startup_use")
    boundaries = _edge_enum(edge_contract, "management_boundary")
    timings = _edge_enum(edge_contract, "timing")
    execution_locations = _edge_enum(edge_contract, "execution_location")
    known_processes = set(process_ids)
    edge_ids: list[str] = []
    seen_ids: set[str] = set()
    pairs: dict[tuple[str, str, str, str], list[dict[str, str]]] = {}
    linked_claim_ids: set[str] = set()
    for raw_edge in raw_edges:
        if not isinstance(raw_edge, Mapping):
            raise ValueError("invalid relationship edge")
        ensure_exact_keys(raw_edge, edge_fields, "relationship edge")
        edge = {key: _edge_identifier(raw_edge.get(key), key) for key in (
            "id", "source_process_id", "target_id", "mechanism", "endpoint_name"
        )}
        if edge["id"] in seen_ids:
            raise ValueError("duplicate graph edge")
        seen_ids.add(edge["id"])
        if edge["source_process_id"] not in known_processes:
            raise ValueError("relationship source process dangling")
        target_kind = raw_edge.get("target_kind")
        if target_kind not in target_kinds:
            raise ValueError("invalid relationship target kind")
        if target_kind == "process" and edge["target_id"] not in known_processes:
            raise ValueError("relationship target process dangling")
        dependency_type = raw_edge.get("dependency_type")
        if dependency_type not in dependency_types:
            raise ValueError("invalid relationship dependency type")
        for field, allowed in (
            ("required_for_function", required_statuses),
            ("startup_use", startup_statuses),
            ("status", edge_statuses),
            ("management_boundary", boundaries),
            ("timing", timings),
            ("execution_location", execution_locations),
        ):
            if raw_edge.get(field) not in allowed:
                raise ValueError(f"invalid relationship {field}")
        edge_claim_ids = raw_edge.get("claim_ids")
        if not isinstance(edge_claim_ids, list) or not edge_claim_ids:
            raise ValueError("relationship claim ids required")
        resolved_claim_ids = [_edge_identifier(value, "claim id") for value in edge_claim_ids]
        if len(resolved_claim_ids) != len(set(resolved_claim_ids)) or not set(resolved_claim_ids).issubset(claims_by_id):
            raise ValueError("relationship claim dangling")
        if raw_edge["status"] == "conflicted" and any(claims_by_id[claim_id] != "conflicted" for claim_id in resolved_claim_ids):
            raise ValueError("conflicted relationship requires conflicted claim")
        linked_claim_ids.update(resolved_claim_ids)
        pair = (edge["source_process_id"], edge["target_id"], target_kind, raw_edge["timing"])
        signature = {
            "dependency_type": dependency_type,
            "mechanism": edge["mechanism"],
            "endpoint_name": edge["endpoint_name"],
            "required_for_function": raw_edge["required_for_function"],
            "startup_use": raw_edge["startup_use"],
            "management_boundary": raw_edge["management_boundary"],
            "execution_location": raw_edge["execution_location"],
        }
        pairs.setdefault(pair, []).append({"status": raw_edge["status"], **signature})
        edge_ids.append(edge["id"])
    for variants in pairs.values():
        signatures = {tuple(sorted(variant.items())) for variant in variants}
        if len(signatures) > 1 and any(variant["status"] != "conflicted" for variant in variants):
            raise ValueError("conflicting relationship must be marked conflicted")
    for claim_id, status in claims_by_id.items():
        if status in {"confirmed", "inferred", "conflicted"} and claim_id not in linked_claim_ids:
            raise ValueError("relationship claim requires graph edge")
    return edge_ids


def promote_relationship_facts(state: PipelineState, payload: Mapping[str, Any]) -> PipelineState:
    """Atomically promote a validated Relationships payload into trusted state."""
    return submit(state, "relationships", dict(payload), state.revision, state.state_hash)


def project_relationships_handoff(state: PipelineState) -> dict[str, list[str]]:
    """Expose only trusted relationship identifiers to the current successor."""
    payload = state.outputs.get("relationships")
    if not isinstance(payload, Mapping):
        raise ValueError("relationships output is unavailable")
    claims = payload.get("claims")
    if not isinstance(claims, list):
        raise ValueError("relationships claims are unavailable")
    return {
        "graph_edge_ids": list(payload.get("graph_edge_ids", [])),
        "relationship_fact_refs": [
            f"fact_relationships_{claim['id']}"
            for claim in claims
            if isinstance(claim, Mapping) and claim.get("status") != "unknown"
        ],
        "unknown_ids": [
            claim["id"]
            for claim in claims
            if isinstance(claim, Mapping) and claim.get("status") == "unknown"
        ],
    }


def validate_boundaries_payload(payload: Mapping[str, Any], registry: ObservationRegistry, snapshot: TargetSnapshot, binding: Mapping[str, Any], discovery_fact_refs: list[str], execution_fact_refs: list[str], relationship_fact_refs: list[str], process_ids: list[str], candidate_ids: list[str]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be object")
    _require_contract_fields("boundaries", payload)
    evidence, claims = payload.get("evidence"), payload.get("claims")
    if not isinstance(evidence, list) or not evidence or not isinstance(claims, list) or not claims:
        raise ValueError("boundaries requires trusted evidence and claims")
    observations: dict[str, dict[str, Any]] = {}
    for item in evidence:
        if isinstance(item, Mapping) and isinstance(item.get("observation_ref"), str):
            observations[item["observation_ref"]] = registry.resolve(item["observation_ref"], "boundaries", snapshot)
    normalized, _ = normalize_submission_payload(payload, observations, binding)
    for field, accepted in (("discovery_fact_refs", discovery_fact_refs), ("execution_fact_refs", execution_fact_refs), ("relationship_fact_refs", relationship_fact_refs)):
        if normalized.get(field) != accepted:
            raise ValueError(f"unknown {field[:-1].replace('_', ' ')}")
    units = normalized.get("workload_units")
    if not isinstance(units, list):
        raise ValueError("invalid workload units")
    known_processes, known_candidates = set(process_ids), set(candidate_ids)
    claim_status = {claim.get("id"): claim.get("status") for claim in normalized["claims"] if isinstance(claim, Mapping)}
    unit_ids: list[str] = []
    deployable_ids: list[str] = []
    assigned: set[str] = set()
    included_candidates: set[str] = set()
    linked_claims: set[str] = set()
    unit_contract = workload_unit_contract()
    required = set(unit_contract)
    condition_statuses = _edge_enum(unit_contract, "start_definition_status")
    lifecycle_statuses = _edge_enum(unit_contract, "lifecycle")
    state_statuses = _edge_enum(unit_contract, "state_decision")
    deployability_statuses = _edge_enum(unit_contract, "deployability_status")

    def link_claims(claim_ids: Any, allowed_statuses: set[str]) -> None:
        if not isinstance(claim_ids, list) or not claim_ids or len(claim_ids) != len(set(claim_ids)) or not set(claim_ids).issubset(claim_status):
            raise ValueError("workload claim dangling")
        if linked_claims.intersection(claim_ids):
            raise ValueError("workload claim duplicate")
        if any(claim_status[claim_id] not in allowed_statuses for claim_id in claim_ids):
            raise ValueError("workload claim status mismatch")
        linked_claims.update(claim_ids)

    for unit in units:
        if not isinstance(unit, Mapping):
            raise ValueError("invalid workload unit")
        ensure_exact_keys(unit, required, "workload unit")
        unit_id = _edge_identifier(unit.get("id"), "unit id")
        if unit_id in unit_ids:
            raise ValueError("duplicate workload unit")
        members = unit.get("process_ids")
        if not isinstance(members, list) or not members or len(members) != len(set(members)) or not set(members).issubset(known_processes):
            raise ValueError("workload process dangling")
        if assigned.intersection(members):
            raise ValueError("duplicate workload process")
        assigned.update(members)
        candidates = unit.get("candidate_ids")
        if not isinstance(candidates, list) or len(candidates) != len(set(candidates)) or not set(candidates).issubset(known_candidates):
            raise ValueError("workload candidate dangling")
        included_candidates.update(candidates)
        if unit.get("start_definition_status") not in condition_statuses or unit.get("independent_lifecycle_status") not in condition_statuses or unit.get("boundary_status") not in condition_statuses:
            raise ValueError("invalid workload boundary status")
        if unit.get("lifecycle") not in lifecycle_statuses or unit.get("state_decision") not in state_statuses or unit.get("deployability_status") not in deployability_statuses or unit_contract.get("deployable") != "boolean" or not isinstance(unit.get("deployable"), bool):
            raise ValueError("invalid workload unit")
        if unit["boundary_status"] == "confirmed" and (unit["start_definition_status"] != "confirmed" or unit["independent_lifecycle_status"] != "confirmed"):
            raise ValueError("confirmed workload requires both boundary conditions")
        if unit["deployable"] and (unit["boundary_status"] != "confirmed" or unit["start_definition_status"] != "confirmed" or unit["independent_lifecycle_status"] != "confirmed"):
            raise ValueError("deployable workload requires both boundary conditions")
        if unit["deployable"] and unit["deployability_status"] not in {"confirmed", "inferred"}:
            raise ValueError("deployable workload requires grounded eligibility")

        link_claims(unit.get("boundary_claim_ids"), {unit["boundary_status"]})
        lifecycle_claim_statuses = {"unknown"} if unit["lifecycle"] == "unknown" else {"confirmed", "inferred"}
        state_claim_statuses = (
            {"unknown"} if unit["state_decision"] == "unknown"
            else {"conflicted"} if unit["state_decision"] == "conflicted"
            else {"confirmed", "inferred"}
        )
        link_claims(unit.get("lifecycle_claim_ids"), lifecycle_claim_statuses)
        link_claims(unit.get("state_claim_ids"), state_claim_statuses)
        link_claims(unit.get("deployability_claim_ids"), {unit["deployability_status"]})
        unit_ids.append(unit_id)
        if unit["deployable"]:
            deployable_ids.append(unit_id)
    if assigned != known_processes:
        raise ValueError("workload process unassigned")
    exclusions = normalized.get("candidate_exclusions")
    if not isinstance(exclusions, list):
        raise ValueError("invalid candidate exclusions")
    exclusion_contract = candidate_exclusion_contract()
    exclusion_fields = set(exclusion_contract)
    dispositions = _edge_enum(exclusion_contract, "disposition")
    excluded_candidates: set[str] = set()
    for exclusion in exclusions:
        if not isinstance(exclusion, Mapping):
            raise ValueError("invalid candidate exclusion")
        ensure_exact_keys(exclusion, exclusion_fields, "candidate exclusion")
        candidate_id = _edge_identifier(exclusion.get("candidate_id"), "candidate id")
        if candidate_id not in known_candidates or candidate_id in included_candidates or candidate_id in excluded_candidates:
            raise ValueError("candidate exclusion dangling")
        disposition = exclusion.get("disposition")
        if disposition not in dispositions:
            raise ValueError("invalid candidate disposition")
        allowed_claim_statuses = {"confirmed", "inferred"} if disposition == "excluded" else {disposition}
        link_claims(exclusion.get("claim_ids"), allowed_claim_statuses)
        excluded_candidates.add(candidate_id)
    if included_candidates | excluded_candidates != known_candidates:
        raise ValueError("workload candidate unaccounted")
    if any(status in {"confirmed", "inferred", "conflicted"} and claim_id not in linked_claims for claim_id, status in claim_status.items()):
        raise ValueError("boundary claim requires workload unit")
    normalized["unit_ids"] = unit_ids
    normalized["deployable_unit_ids"] = deployable_ids
    normalized["included_candidate_ids"] = [candidate_id for candidate_id in candidate_ids if candidate_id in included_candidates]
    normalized["excluded_candidate_ids"] = [candidate_id for candidate_id in candidate_ids if candidate_id in excluded_candidates]
    return normalized


def promote_boundary_facts(state: PipelineState, payload: Mapping[str, Any]) -> PipelineState:
    return submit(state, "boundaries", dict(payload), state.revision, state.state_hash)


def project_boundaries_handoff(state: PipelineState) -> dict[str, list[str]]:
    payload = state.outputs.get("boundaries")
    if not isinstance(payload, Mapping) or not isinstance(payload.get("claims"), list):
        raise ValueError("boundaries output is unavailable")
    claims = payload["claims"]
    return {"unit_ids": list(payload.get("unit_ids", [])), "deployable_unit_ids": list(payload.get("deployable_unit_ids", [])), "included_candidate_ids": list(payload.get("included_candidate_ids", [])), "excluded_candidate_ids": list(payload.get("excluded_candidate_ids", [])), "boundaries_fact_refs": [f"fact_boundaries_{claim['id']}" for claim in claims if isinstance(claim, Mapping) and claim.get("status") != "unknown"], "unknown_ids": [claim["id"] for claim in claims if isinstance(claim, Mapping) and claim.get("status") == "unknown"]}
