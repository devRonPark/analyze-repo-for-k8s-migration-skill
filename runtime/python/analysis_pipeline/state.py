from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
import hashlib
import json
from typing import Any, Mapping


ANALYSIS_STAGES = ("discovery", "execution", "relationships", "boundaries", "contracts")
FINAL_STAGE = "finalize"


def canonical_json(value: Any) -> str:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int):
        return json.dumps(value)
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError("non-finite canonical value")
        return json.dumps(int(value))
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonical_json(item) for item in value) + "]"
    if isinstance(value, Mapping):
        items = []
        for key in sorted(value):
            if not isinstance(key, str):
                raise ValueError("canonical object keys must be strings")
            items.append(f"{json.dumps(key, ensure_ascii=False)}:{canonical_json(value[key])}")
        return "{" + ",".join(items) + "}"
    raise ValueError("unsupported canonical value")


def _sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def derive_evidence_id(value: Mapping[str, Any]) -> str:
    required = {"snapshot_hash", "location", "range", "status", "content_fingerprint"}
    missing = required.difference(value.keys())
    if missing:
        raise ValueError(f"missing evidence id fields: {sorted(missing)}")
    return "ev_" + _sha256({key: value[key] for key in sorted(required)})[:32]


def normalize_binding(binding: str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(binding, str):
        if not binding:
            raise ValueError("binding required")
        return {
            "binding_id": binding,
            "target_realpath": "",
            "target_snapshot_hash": binding,
            "skill_manifest_hash": "",
            "required_rule_ids": [],
        }
    if not isinstance(binding, Mapping):
        raise ValueError("binding required")
    normalized = deepcopy(dict(binding))
    required = ("binding_id", "target_realpath", "target_snapshot_hash", "skill_manifest_hash", "required_rule_ids")
    for key in required:
        if key not in normalized:
            raise ValueError(f"binding missing {key}")
    if not isinstance(normalized["required_rule_ids"], list):
        raise ValueError("binding required_rule_ids must be a list")
    return normalized


def empty_catalog() -> dict[str, list[str]]:
    return {
        "process_ids": [],
        "candidate_ids": [],
        "graph_edge_ids": [],
        "unit_ids": [],
        "deployable_unit_ids": [],
        "contract_ids": [],
        "decision_ids": [],
    }


@dataclass(frozen=True)
class PipelineState:
    binding: dict[str, Any]
    revision: int = 0
    current_stage: str = ANALYSIS_STAGES[0]
    finalized: bool = False
    outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    catalog: dict[str, list[str]] = field(default_factory=empty_catalog)
    reopen_reasons: tuple[str, ...] = ()
    created_at: str = "1970-01-01T00:00:00.000Z"
    state_hash: str = ""

    def digest(self) -> str:
        return _sha256(
            {
                "binding": self.binding,
                "revision": self.revision,
                "current_stage": self.current_stage,
                "finalized": self.finalized,
                "outputs": self.outputs,
                "evidence": self.evidence,
                "catalog": self.catalog,
                "reopen_reasons": self.reopen_reasons,
                "created_at": self.created_at,
            }
        )


def with_hash(state: PipelineState) -> PipelineState:
    return replace(state, state_hash=state.digest())


def create_state(binding: str | Mapping[str, Any]) -> PipelineState:
    return with_hash(PipelineState(binding=normalize_binding(binding)))
