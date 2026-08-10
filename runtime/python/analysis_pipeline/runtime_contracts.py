"""Bind accepted semantic facts to resolved WorkloadUnits without copying values."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .validation import CLAIM_STATUSES
from .workload_grouping import derive_workload_unit_id, validate_workload_grouping


PROJECT_FACT_KINDS = frozenset({
    "application.name",
    "project.language",
    "project.language_version",
    "project.framework",
})
BUILD_FACT_KINDS = frozenset({"build.tool", "build.artifact_type", "build.command"})
RUNTIME_FACT_FIELDS = {
    "start_command_fact_ref": "runtime.start_command",
    "listening_port_fact_ref": "runtime.listening_port",
    "server_fact_ref": "runtime.server",
    "context_path_fact_ref": "runtime.context_path",
}
REQUIRED_RUNTIME_FACT_FIELDS = frozenset({"start_command_fact_ref", "listening_port_fact_ref"})
_CONTRACT_FIELDS = {"unit_id", "project_fact_refs", "build_fact_refs", "runtime", "fact_statuses"}


def _fact_index(semantic_facts: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    if not isinstance(semantic_facts, (list, tuple)):
        raise ValueError("invalid accepted semantic facts")
    facts: dict[str, Mapping[str, Any]] = {}
    for fact in semantic_facts:
        if not isinstance(fact, Mapping):
            raise ValueError("invalid accepted semantic fact")
        ref, kind, status = fact.get("ref"), fact.get("kind"), fact.get("status")
        if not isinstance(ref, str) or not isinstance(kind, str) or status not in CLAIM_STATUSES:
            raise ValueError("invalid accepted semantic fact")
        if ref in facts:
            raise ValueError("duplicate accepted semantic fact ref")
        facts[ref] = fact
    return facts


def _resolved_units(
    units: Sequence[Mapping[str, Any]], runtime_processes: Sequence[Mapping[str, Any]],
) -> dict[str, set[str]]:
    if not isinstance(units, (list, tuple)) or not units:
        raise ValueError("resolved workload units required")
    if not isinstance(runtime_processes, (list, tuple)) or not runtime_processes:
        raise ValueError("accepted runtime processes required")
    process_ids = [process.get("id") for process in runtime_processes if isinstance(process, Mapping)]
    if len(process_ids) != len(runtime_processes) or any(not isinstance(process_id, str) for process_id in process_ids):
        raise ValueError("invalid accepted runtime process")

    groups: list[dict[str, Any]] = []
    unit_fact_refs: dict[str, set[str]] = {}
    for unit in units:
        if not isinstance(unit, Mapping):
            raise ValueError("invalid resolved workload unit")
        unit_id, member_ids = unit.get("unit_id"), unit.get("process_ids")
        if not isinstance(unit_id, str) or not isinstance(member_ids, list) or not member_ids:
            raise ValueError("invalid resolved workload unit")
        if unit_id != derive_workload_unit_id(member_ids):
            raise ValueError("forged workload unit id")
        groups.append({"unit_id": unit_id, "process_ids": member_ids})
        members = set(member_ids)
        unit_fact_refs[unit_id] = {
            ref
            for process in runtime_processes
            if isinstance(process, Mapping) and process.get("id") in members
            for ref in process.get("semantic_fact_refs", [])
            if isinstance(ref, str)
        }
    validate_workload_grouping(process_ids, groups)
    return unit_fact_refs


def _select_runtime_ref(
    fact_kind: str, unit_refs: set[str], facts: Mapping[str, Mapping[str, Any]], *, required: bool,
) -> str | None:
    matches = sorted(ref for ref in unit_refs if ref in facts and facts[ref].get("kind") == fact_kind)
    if len(matches) > 1:
        raise ValueError(f"ambiguous runtime fact {fact_kind}")
    if matches:
        return matches[0]
    if required:
        if any(fact.get("kind") == fact_kind for fact in facts.values()):
            raise ValueError(f"runtime fact subject mismatch: {fact_kind}")
        raise ValueError(f"missing runtime fact {fact_kind}")
    return None


def resolve_runtime_contracts(
    units: Sequence[Mapping[str, Any]],
    runtime_processes: Sequence[Mapping[str, Any]],
    semantic_facts: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Create one value-free RuntimeContract for every resolved WorkloadUnit.

    Inputs are accepted D01/D02/D03/D04 outputs. This function deliberately
    uses only their identifiers, kinds, and statuses; it does not inspect
    repository evidence or re-derive semantic values.
    """
    facts = _fact_index(semantic_facts)
    unit_fact_refs = _resolved_units(units, runtime_processes)
    project_refs = sorted(ref for ref, fact in facts.items() if fact.get("kind") in PROJECT_FACT_KINDS)
    build_refs = sorted(ref for ref, fact in facts.items() if fact.get("kind") in BUILD_FACT_KINDS)
    contracts: list[dict[str, Any]] = []
    for unit_id in sorted(unit_fact_refs):
        runtime: dict[str, str] = {}
        for field, kind in RUNTIME_FACT_FIELDS.items():
            ref = _select_runtime_ref(kind, unit_fact_refs[unit_id], facts, required=field in REQUIRED_RUNTIME_FACT_FIELDS)
            if ref is not None:
                runtime[field] = ref
        refs = [*project_refs, *build_refs, *runtime.values()]
        contracts.append({
            "unit_id": unit_id,
            "project_fact_refs": project_refs,
            "build_fact_refs": build_refs,
            "runtime": runtime,
            "fact_statuses": {ref: facts[ref]["status"] for ref in refs},
        })
    validate_runtime_contracts(units, runtime_processes, semantic_facts, contracts)
    return contracts


def validate_runtime_contracts(
    units: Sequence[Mapping[str, Any]],
    runtime_processes: Sequence[Mapping[str, Any]],
    semantic_facts: Sequence[Mapping[str, Any]],
    contracts: Sequence[Mapping[str, Any]],
) -> None:
    """Reject dangling, cross-unit, wrong-kind, and value-bearing contracts."""
    facts = _fact_index(semantic_facts)
    unit_fact_refs = _resolved_units(units, runtime_processes)
    if not isinstance(contracts, (list, tuple)) or len(contracts) != len(unit_fact_refs):
        raise ValueError("one runtime contract per resolved workload unit required")
    seen_units: set[str] = set()
    for contract in contracts:
        if not isinstance(contract, Mapping) or set(contract) != _CONTRACT_FIELDS:
            raise ValueError("invalid runtime contract")
        unit_id = contract.get("unit_id")
        if not isinstance(unit_id, str) or unit_id not in unit_fact_refs or unit_id in seen_units:
            raise ValueError("runtime contract unit binding mismatch")
        seen_units.add(unit_id)
        project_refs, build_refs, runtime, statuses = (
            contract.get("project_fact_refs"), contract.get("build_fact_refs"),
            contract.get("runtime"), contract.get("fact_statuses"),
        )
        if not isinstance(project_refs, list) or not isinstance(build_refs, list) or not isinstance(runtime, Mapping) or not isinstance(statuses, Mapping):
            raise ValueError("invalid runtime contract")
        if set(runtime).difference(RUNTIME_FACT_FIELDS):
            raise ValueError("invalid runtime contract runtime field")
        for field in REQUIRED_RUNTIME_FACT_FIELDS:
            if field not in runtime:
                raise ValueError(f"missing runtime contract field {field}")
        refs = [*project_refs, *build_refs, *runtime.values()]
        if any(not isinstance(ref, str) or ref not in facts for ref in refs):
            raise ValueError("runtime contract fact dangling")
        if len(refs) != len(set(refs)):
            raise ValueError("duplicate runtime contract fact ref")
        if any(facts[ref].get("kind") not in PROJECT_FACT_KINDS for ref in project_refs):
            raise ValueError("runtime contract project fact kind mismatch")
        if any(facts[ref].get("kind") not in BUILD_FACT_KINDS for ref in build_refs):
            raise ValueError("runtime contract build fact kind mismatch")
        for field, ref in runtime.items():
            if facts[ref].get("kind") != RUNTIME_FACT_FIELDS[field]:
                raise ValueError("runtime contract runtime fact kind mismatch")
            if ref not in unit_fact_refs[unit_id]:
                raise ValueError("runtime fact subject mismatch")
        if set(statuses) != set(refs) or any(statuses[ref] != facts[ref].get("status") for ref in refs):
            raise ValueError("runtime contract fact status mismatch")
    if seen_units != set(unit_fact_refs):
        raise ValueError("one runtime contract per resolved workload unit required")
