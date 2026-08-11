"""One-shot state shared by the host continuation and its OpenCode guard."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class HostActivationStateError(ValueError):
    """The host cannot safely publish an activation ownership record."""


def write_host_activation_state(
    path: Path,
    *,
    analysis_id: str | None,
    revision: int,
    transition_token: str | None,
    next_skill: str,
) -> None:
    """Atomically publish the exact accepted handoff owned by the host.

    The OpenCode plugin consumes this record only while it is pending. It is
    deliberately outside ``stage_input``: it governs context materialization,
    not the stage payload.
    """
    if not isinstance(analysis_id, str) or not analysis_id:
        raise HostActivationStateError("invalid_analysis_id")
    if not isinstance(revision, int) or revision < 0:
        raise HostActivationStateError("invalid_revision")
    if not isinstance(transition_token, str) or not transition_token:
        raise HostActivationStateError("invalid_transition_token")
    if not isinstance(next_skill, str) or not next_skill:
        raise HostActivationStateError("missing_next_skill")

    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "version": 1,
        "state": "pending",
        "transition_owner": "host",
        "analysis_id": analysis_id,
        "revision": revision,
        "transition_token": transition_token,
        "next_skill": next_skill,
    }
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    except OSError as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise HostActivationStateError("activation_state_write_failed") from error
