"""Narrow, fail-closed host ownership for an already-accepted handoff."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


TRANSITION_MODES = frozenset({"model_routed", "host_owned"})


class HostContinuationError(ValueError):
    """A server-issued handoff could not be safely activated by the host."""


def load_host_continuation(
    handoff: Mapping[str, Any],
    *,
    analysis_id: str | None,
    revision: int,
    transition_token: str | None,
    expected_skill: str | None,
    skill_root: Path,
) -> dict[str, Any]:
    """Load exactly the server-issued next Skill after validating its binding.

    This function never selects a stage or alters the handoff.  It only makes
    the already-issued next Skill available in the same trusted MCP response.
    """
    if handoff.get("status") != "accepted":
        raise HostContinuationError("handoff_not_accepted")
    next_skill = handoff.get("next_skill")
    if not isinstance(next_skill, str) or not next_skill:
        raise HostContinuationError("missing_next_skill")
    if next_skill != expected_skill:
        raise HostContinuationError("unexpected_next_skill")
    if handoff.get("analysis_id") != analysis_id:
        raise HostContinuationError("invalid_analysis_id")
    if handoff.get("revision") != revision:
        raise HostContinuationError("invalid_revision")
    if handoff.get("transition_token") != transition_token:
        raise HostContinuationError("invalid_transition_token")

    root = skill_root.resolve()
    skill_path = (root / next_skill / "SKILL.md").resolve()
    try:
        skill_path.relative_to(root)
    except ValueError as error:
        raise HostContinuationError("unknown_next_skill") from error
    if not skill_path.is_file():
        raise HostContinuationError("unknown_next_skill")
    try:
        skill_content = skill_path.read_text(encoding="utf-8")
    except OSError as error:
        raise HostContinuationError("skill_load_failed") from error
    if not skill_content.strip():
        raise HostContinuationError("skill_load_failed")

    return {
        "transition_owner": "host",
        "requested_skill": next_skill,
        "skill_load": "completed",
        "activation": (
            f"Host-owned continuation: the trusted host loaded `{next_skill}` from the accepted "
            "handoff. Do not call skill; apply the loaded Skill's current-stage procedure now."
        ),
        "skill_content": skill_content,
    }
