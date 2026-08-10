"""Structural validation for the Boundaries stage's process-to-unit grouping.

Grouping is the one part of a Workload Unit decision that a single accepted
runtime process can answer by itself: with nothing else to compare against,
"one process, one unit" is the only possible grouping. This module isolates
that structural check (every accepted process assigned to exactly one group,
no duplicates, no dangling references) from the richer per-unit decisions
(deployability, lifecycle, state) that do need comparative evidence once a
group holds more than one process.
"""
from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from .state import canonical_json
from .validation import derive_runtime_process_id


def derive_workload_unit_id(process_ids: Sequence[str]) -> str:
    """Derive the stable, server-owned identifier for a Workload Unit."""
    if (
        not isinstance(process_ids, (list, tuple))
        or not process_ids
        or any(not isinstance(process_id, str) or not process_id for process_id in process_ids)
        or len(process_ids) != len(set(process_ids))
    ):
        raise ValueError("invalid workload grouping input")
    identity = {"process_ids": sorted(process_ids)}
    return "unit_" + hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()[:24]


def resolve_workload_grouping(runtime_processes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Resolve the one supported deterministic RuntimeProcess grouping.

    The D03 RuntimeProcess is the semantic source of truth.  This intentionally
    makes no lifecycle, controller, contract, or state decision: one accepted
    process has no sibling against which a split or merge could be established.
    """
    if not isinstance(runtime_processes, (list, tuple)) or len(runtime_processes) != 1:
        raise ValueError("single runtime process required for workload grouping")
    process = runtime_processes[0]
    if not isinstance(process, Mapping):
        raise ValueError("invalid runtime process")

    identity = {
        field: process.get(field)
        for field in ("candidate_ids", "role", "execution_pattern", "semantic_fact_refs")
    }
    process_id = process.get("id")
    if process_id != derive_runtime_process_id(identity):
        raise ValueError("forged runtime process id")
    candidate_ids = identity["candidate_ids"]
    if (
        not isinstance(candidate_ids, list)
        or not candidate_ids
        or any(not isinstance(candidate_id, str) or not candidate_id for candidate_id in candidate_ids)
        or len(candidate_ids) != len(set(candidate_ids))
    ):
        raise ValueError("invalid runtime process candidates")

    unit_id = derive_workload_unit_id([process_id])
    return {
        "input_process_ids": [process_id],
        "groups": [{
            "unit_id": unit_id,
            "process_ids": [process_id],
            "candidate_ids": list(candidate_ids),
        }],
    }


def validate_workload_grouping(input_process_ids: Sequence[str], groups: Sequence[Mapping[str, Any]]) -> set[str]:
    """Validate that `groups` exactly partitions `input_process_ids`.

    Returns the set of group `unit_id`s that are deterministic: reachable with
    no comparative evidence at all. This is exactly the case where the
    accepted process set has exactly one member -- there is no second process
    to compare an independent lifecycle against, so the single process is
    necessarily its own group. A process that is merely alone within its own
    group (e.g. one leg of a split among several accepted processes) is not
    deterministic in this sense: the split itself still needs comparative
    evidence, so callers should still require it there.
    """
    if not isinstance(input_process_ids, (list, tuple)) or not input_process_ids:
        raise ValueError("invalid workload grouping input")
    if len(input_process_ids) != len(set(input_process_ids)) or any(not isinstance(pid, str) for pid in input_process_ids):
        raise ValueError("invalid workload grouping input")
    known = set(input_process_ids)

    if not isinstance(groups, (list, tuple)) or not groups:
        raise ValueError("invalid workload grouping")

    assigned: set[str] = set()
    group_ids: set[str] = set()
    for group in groups:
        if not isinstance(group, Mapping):
            raise ValueError("invalid workload group")
        group_id = group.get("unit_id")
        if not isinstance(group_id, str) or not group_id:
            raise ValueError("invalid workload group id")
        if group_id in group_ids:
            raise ValueError("duplicate workload group id")
        group_ids.add(group_id)

        members = group.get("process_ids")
        if not isinstance(members, (list, tuple)) or not members or any(not isinstance(pid, str) for pid in members):
            raise ValueError("invalid workload group process ids")
        if len(members) != len(set(members)):
            raise ValueError("duplicate workload group process")
        if not set(members).issubset(known):
            raise ValueError("dangling workload group process")
        if assigned.intersection(members):
            raise ValueError("duplicate workload group process")
        assigned.update(members)

    if assigned != known:
        raise ValueError("workload group process unassigned")

    return set(group_ids) if len(known) == 1 else set()
