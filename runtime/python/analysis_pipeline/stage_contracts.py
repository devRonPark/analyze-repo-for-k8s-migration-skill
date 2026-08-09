"""Load the single stage-payload contract source of truth."""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Mapping

from .observations import ObservationRegistry, TargetSnapshot
from .state import PipelineState
from .transitions import submit
from .validation import normalize_submission_payload

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


def _require_contract_fields(stage: str, payload: Mapping[str, Any]) -> None:
    if missing := client_payload_required_fields(stage).difference(payload):
        raise ValueError(f"missing {stage} payload field")


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
