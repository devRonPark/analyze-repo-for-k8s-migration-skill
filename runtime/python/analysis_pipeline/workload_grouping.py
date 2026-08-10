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

from typing import Any, Mapping, Sequence


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
