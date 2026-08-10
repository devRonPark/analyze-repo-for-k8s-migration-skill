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
from .workload_grouping import validate_workload_grouping

CONTRACT_PATH = Path(__file__).resolve().parents[3] / "contracts" / "stage-payload-contracts.json"
REPORT_STATE_PATH = Path(__file__).resolve().parents[3] / "contracts" / "accepted-report-state.schema.json"


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


def report_state_contract() -> dict[str, Any]:
    try:
        state = json.loads(REPORT_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_report_state_contract") from exc
    if state.get("schema_version") != 1 or not isinstance(state.get("report_slot"), Mapping) or not isinstance(state.get("slot_definitions"), Mapping) or not isinstance(state.get("modes"), Mapping):
        raise ValueError("invalid_report_state_contract")
    return state


def required_report_slot_ids(mode: str) -> list[str]:
    mode_contract = report_state_contract()["modes"].get(mode)
    slots = mode_contract.get("required_report_slots") if isinstance(mode_contract, Mapping) else None
    if not isinstance(slots, list) or not slots or len(slots) != len(set(slots)) or any(not isinstance(slot, str) or not _IDENTIFIER.fullmatch(slot) for slot in slots):
        raise ValueError("invalid_report_state_contract")
    return list(slots)


def report_slot_definition(slot_id: str) -> dict[str, Any]:
    definition = report_state_contract()["slot_definitions"].get(slot_id)
    stages = definition.get("allowed_fact_stages") if isinstance(definition, Mapping) else None
    if not isinstance(stages, list) or not stages or len(stages) != len(set(stages)) or any(stage not in {"discovery", "execution", "relationships", "boundaries"} for stage in stages):
        raise ValueError("invalid_report_state_contract")
    return dict(definition)


def assign_report_slot_facts(required_slots: list[str], fact_statuses: Mapping[str, str]) -> dict[str, str | None]:
    """Greedily assign at most one predecessor fact per report slot.

    Each accepted predecessor fact can ground only one slot (see "report slot
    fact duplicate" in validate_contracts_payload below), so this claims one
    available fact per slot in required_slots order rather than just checking
    allowed-stage availability, which would let every slot look groundable
    even when the fact pool is smaller than the slot count. A slot mapped to
    None has no unclaimed eligible predecessor fact and needs its own fresh
    Contracts-stage claim and evidence instead.
    """
    remaining = {ref for ref in fact_statuses}
    assignment: dict[str, str | None] = {}
    for slot_id in required_slots:
        allowed = set(report_slot_definition(slot_id).get("allowed_fact_stages", ()))
        claimable = next((ref for ref in sorted(remaining) if ref.split("_", 2)[1] in allowed), None)
        assignment[slot_id] = claimable
        if claimable is not None:
            remaining.discard(claimable)
    return assignment


def project_predecessor_fact_statuses(state: PipelineState) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for stage in ("discovery", "execution", "relationships", "boundaries"):
        payload = state.outputs.get(stage)
        claims = payload.get("claims") if isinstance(payload, Mapping) else None
        if not isinstance(claims, list):
            raise ValueError("predecessor facts are unavailable")
        for claim in claims:
            if not isinstance(claim, Mapping) or not isinstance(claim.get("id"), str) or claim.get("status") not in CLAIM_STATUSES:
                raise ValueError("predecessor claim is invalid")
            if claim["status"] != "unknown":
                statuses[f"fact_{stage}_{claim['id']}"] = claim["status"]
    return statuses


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
    linked_claim_owners: dict[str, str] = {}
    unit_contract = workload_unit_contract()
    required = set(unit_contract)
    condition_statuses = _edge_enum(unit_contract, "start_definition_status")
    lifecycle_statuses = _edge_enum(unit_contract, "lifecycle")
    state_statuses = _edge_enum(unit_contract, "state_decision")
    deployability_statuses = _edge_enum(unit_contract, "deployability_status")

    def link_claims(claim_ids: Any, allowed_statuses: set[str], owner: str) -> None:
        """Generic single-field link/check, unchanged in behavior: used only
        where per-field aggregation is out of this hotfix's scope (candidate
        exclusions)."""
        if not isinstance(claim_ids, list) or not claim_ids or len(claim_ids) != len(set(claim_ids)) or not set(claim_ids).issubset(claim_status):
            raise ValueError("workload claim dangling")
        if any(claim_id in linked_claim_owners for claim_id in claim_ids):
            raise ValueError("workload claim duplicate")
        if any(claim_status[claim_id] not in allowed_statuses for claim_id in claim_ids):
            raise ValueError("workload claim status mismatch")
        for claim_id in claim_ids:
            linked_claim_owners[claim_id] = owner

    def field_claim_errors(field_name: str, claim_ids: Any, allowed_statuses: set[str], reason: str) -> tuple[list[str], list[str]]:
        """Collect every problem with one *_claim_ids field instead of raising
        on the first one, so a caller can report all of a unit's wiring
        problems together. Returns (problem descriptions, well-formed claim ids)."""
        if not isinstance(claim_ids, list) or not claim_ids:
            return [f"{field_name} requires at least one claim because {reason}"], []
        errors: list[str] = []
        if len(claim_ids) != len(set(claim_ids)):
            errors.append(f"{field_name} lists the same claim id more than once")
        unique_ids = list(dict.fromkeys(claim_ids))
        dangling = sorted(claim_id for claim_id in unique_ids if claim_id not in claim_status)
        if dangling:
            errors.append(f"{field_name} references unknown claim id(s): {', '.join(dangling)}")
        known_ids = [claim_id for claim_id in unique_ids if claim_id in claim_status]
        mismatched = [claim_id for claim_id in known_ids if claim_status[claim_id] not in allowed_statuses]
        if mismatched:
            expected = "/".join(sorted(allowed_statuses))
            details = ", ".join(f"'{claim_id}' has status '{claim_status[claim_id]}'" for claim_id in mismatched)
            errors.append(f"{field_name} expects claim status '{expected}' but {details}")
        well_formed = [claim_id for claim_id in known_ids if claim_id not in mismatched]
        return errors, well_formed

    def link_workload_claims(unit_id: str, field_specs: list[tuple[str, Any, set[str], str]]) -> None:
        """Aggregate claim-link problems across a unit's four *_claim_ids
        fields into a single rejection, instead of reporting only the first
        field a model happened to get wrong (see HOTFIX 1.6)."""
        unit_errors: list[str] = []
        field_valid_ids: dict[str, list[str]] = {}
        for field_name, claim_ids, allowed_statuses, reason in field_specs:
            errors, valid_ids = field_claim_errors(field_name, claim_ids, allowed_statuses, reason)
            unit_errors.extend(errors)
            field_valid_ids[field_name] = valid_ids

        claimed_within_unit: dict[str, str] = {}
        for field_name, valid_ids in field_valid_ids.items():
            for claim_id in valid_ids:
                owner = linked_claim_owners.get(claim_id) or claimed_within_unit.get(claim_id)
                if owner is not None and owner != field_name:
                    unit_errors.append(f"claim '{claim_id}' is already linked by {owner} and cannot also be linked by {field_name}")
                else:
                    claimed_within_unit[claim_id] = field_name

        if unit_errors:
            raise ValueError(f"workload unit '{unit_id}' has invalid claim links: " + "; ".join(unit_errors))

        for field_name, valid_ids in field_valid_ids.items():
            for claim_id in valid_ids:
                linked_claim_owners[claim_id] = field_name

    try:
        deterministic_unit_ids = validate_workload_grouping(
            process_ids,
            [{"unit_id": u.get("id"), "process_ids": u.get("process_ids")} for u in units if isinstance(u, Mapping)],
        )
    except ValueError:
        # Malformed structure (dangling/duplicate/missing process, bad id) is
        # reported by the per-unit checks below with their existing messages;
        # no unit is treated as a deterministic single-process group here.
        deterministic_unit_ids = set()

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
        # A single accepted runtime process has no sibling to compare an
        # independent lifecycle against, so Workload Grouping is deterministic
        # and independent_lifecycle_status is not required to be confirmed.
        lifecycle_confirmed = unit_id in deterministic_unit_ids or unit["independent_lifecycle_status"] == "confirmed"
        if unit["boundary_status"] == "confirmed" and (unit["start_definition_status"] != "confirmed" or not lifecycle_confirmed):
            raise ValueError("confirmed workload requires both boundary conditions")
        if unit["deployable"] and (unit["boundary_status"] != "confirmed" or unit["start_definition_status"] != "confirmed" or not lifecycle_confirmed):
            raise ValueError("deployable workload requires both boundary conditions")
        if unit["deployable"] and unit["deployability_status"] not in {"confirmed", "inferred"}:
            raise ValueError("deployable workload requires grounded eligibility")

        lifecycle_claim_statuses = {"unknown"} if unit["lifecycle"] == "unknown" else {"confirmed", "inferred"}
        state_claim_statuses = (
            {"unknown"} if unit["state_decision"] == "unknown"
            else {"conflicted"} if unit["state_decision"] == "conflicted"
            else {"confirmed", "inferred"}
        )
        link_workload_claims(unit_id, [
            ("boundary_claim_ids", unit.get("boundary_claim_ids"), {unit["boundary_status"]}, f"boundary_status={unit['boundary_status']}"),
            ("lifecycle_claim_ids", unit.get("lifecycle_claim_ids"), lifecycle_claim_statuses, f"lifecycle={unit['lifecycle']}"),
            ("state_claim_ids", unit.get("state_claim_ids"), state_claim_statuses, f"state_decision={unit['state_decision']}"),
            ("deployability_claim_ids", unit.get("deployability_claim_ids"), {unit["deployability_status"]}, f"deployability_status={unit['deployability_status']}"),
        ])
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
        link_claims(exclusion.get("claim_ids"), allowed_claim_statuses, f"candidate_exclusions[{candidate_id}].claim_ids")
        excluded_candidates.add(candidate_id)
    if included_candidates | excluded_candidates != known_candidates:
        raise ValueError("workload candidate unaccounted")
    if any(status in {"confirmed", "inferred", "conflicted"} and claim_id not in linked_claim_owners for claim_id, status in claim_status.items()):
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


def validate_contracts_payload(payload: Mapping[str, Any], registry: ObservationRegistry, snapshot: TargetSnapshot, binding: Mapping[str, Any], mode: str, discovery_fact_refs: list[str], execution_fact_refs: list[str], relationship_fact_refs: list[str], boundaries_fact_refs: list[str], fact_statuses: Mapping[str, str]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be object")
    _require_contract_fields("contracts", payload)
    evidence, claims = payload.get("evidence"), payload.get("claims")
    if not isinstance(evidence, list) or not evidence or not isinstance(claims, list) or not claims:
        raise ValueError("contracts requires trusted evidence and claims")
    observations: dict[str, dict[str, Any]] = {}
    for item in evidence:
        if isinstance(item, Mapping) and isinstance(item.get("observation_ref"), str):
            observations[item["observation_ref"]] = registry.resolve(item["observation_ref"], "contracts", snapshot)
    normalized, _ = normalize_submission_payload(payload, observations, binding)
    accepted_by_field = {
        "discovery_fact_refs": discovery_fact_refs,
        "execution_fact_refs": execution_fact_refs,
        "relationship_fact_refs": relationship_fact_refs,
        "boundaries_fact_refs": boundaries_fact_refs,
    }
    for field, accepted in accepted_by_field.items():
        if normalized.get(field) != accepted:
            raise ValueError(f"unknown {field[:-1].replace('_', ' ')}")
    expected_slots = required_report_slot_ids(mode)
    report_contract = report_state_contract()
    slot_contract = report_contract["report_slot"]
    slot_fields = set(slot_contract)
    statuses = _edge_enum(slot_contract, "status")
    slots = normalized.get("report_slots")
    if not isinstance(slots, list):
        raise ValueError("invalid report slots")
    claim_status = {claim.get("id"): claim.get("status") for claim in normalized["claims"] if isinstance(claim, Mapping)}
    known_fact_refs = {fact_ref for values in accepted_by_field.values() for fact_ref in values}
    if set(fact_statuses) != known_fact_refs or any(status not in CLAIM_STATUSES - {"unknown"} for status in fact_statuses.values()):
        raise ValueError("invalid predecessor fact status")
    seen_slots: set[str] = set()
    linked_claims: set[str] = set()
    linked_fact_refs: set[str] = set()
    linked_evidence_ids: set[str] = set()
    for slot in slots:
        if not isinstance(slot, Mapping):
            raise ValueError("invalid report slot")
        ensure_exact_keys(slot, slot_fields, "report slot")
        slot_id = _edge_identifier(slot.get("id"), "report slot id")
        if slot_id in seen_slots:
            raise ValueError("duplicate report slot")
        seen_slots.add(slot_id)
        allowed_fact_stages = set(report_slot_definition(slot_id)["allowed_fact_stages"])
        status = slot.get("status")
        if status not in statuses:
            raise ValueError("invalid report slot status")
        fact_refs = slot.get("fact_refs")
        if not isinstance(fact_refs, list) or len(fact_refs) != len(set(fact_refs)) or not set(fact_refs).issubset(known_fact_refs):
            raise ValueError("report slot fact dangling")
        if any(fact_ref.split("_", 2)[1] not in allowed_fact_stages for fact_ref in fact_refs):
            raise ValueError("report slot fact stage mismatch")
        if any(fact_statuses[fact_ref] != status for fact_ref in fact_refs):
            raise ValueError("report slot fact status mismatch")
        if linked_fact_refs.intersection(fact_refs):
            raise ValueError("report slot fact duplicate")
        claim_ids = slot.get("claim_ids")
        if not isinstance(claim_ids, list) or len(claim_ids) != len(set(claim_ids)) or not set(claim_ids).issubset(claim_status):
            raise ValueError("report slot claim dangling")
        if not fact_refs and not claim_ids:
            raise ValueError("report slot lacks evidence")
        if any(claim_status[claim_id] != status for claim_id in claim_ids):
            raise ValueError("report slot claim status mismatch")
        if linked_claims.intersection(claim_ids):
            raise ValueError("report slot claim duplicate")
        slot_evidence_ids = {
            evidence_id
            for claim in normalized["claims"]
            if isinstance(claim, Mapping) and claim.get("id") in claim_ids
            for evidence_id in claim.get("evidence_ids", [])
        }
        if linked_evidence_ids.intersection(slot_evidence_ids):
            raise ValueError("report slot evidence duplicate")
        linked_evidence_ids.update(slot_evidence_ids)
        if status == "unknown" and not claim_ids:
            raise ValueError("unknown report slot requires scoped claim")
        linked_claims.update(claim_ids)
        linked_fact_refs.update(fact_refs)
    if seen_slots != set(expected_slots):
        raise ValueError("report slots do not close the selected mode")
    if set(claim_status) != linked_claims:
        raise ValueError("contracts claim requires report slot")
    normalized["report_slot_ids"] = expected_slots
    normalized["contract_ids"] = [f"contract_{slot_id.replace('-', '_').replace('.', '_')}" for slot_id in expected_slots]
    return normalized


def promote_contract_facts(state: PipelineState, payload: Mapping[str, Any]) -> PipelineState:
    return submit(state, "contracts", dict(payload), state.revision, state.state_hash)


def project_contracts_handoff(state: PipelineState) -> dict[str, list[str]]:
    payload = state.outputs.get("contracts")
    if not isinstance(payload, Mapping) or not isinstance(payload.get("claims"), list):
        raise ValueError("contracts output is unavailable")
    claims = payload["claims"]
    return {
        "contract_ids": list(payload.get("contract_ids", [])),
        "report_slot_ids": list(payload.get("report_slot_ids", [])),
        "unknown_ids": [claim["id"] for claim in claims if isinstance(claim, Mapping) and claim.get("status") == "unknown"],
    }
