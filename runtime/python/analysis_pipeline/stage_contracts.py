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
    required = {
        "schema_version", "stage", "evidence", "claims", "rule_applications",
        "signals", "candidate_ids", "decisions",
    }
    if missing := required.difference(payload):
        raise ValueError("missing discovery payload field")
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
