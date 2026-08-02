"""Provider-neutral protocol types shared by Agent Tool boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Sequence


class ToolErrorCode(StrEnum):
    """Stable domain error codes exposed to the model."""

    INVALID_TOOL_NAME = "invalid_tool_name"
    MALFORMED_ARGUMENTS = "malformed_arguments"
    INVALID_ARGUMENTS = "invalid_arguments"
    FORBIDDEN_PATH = "forbidden_path"
    NOT_FOUND = "not_found"
    DUPLICATE_CALL = "duplicate_call"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CANDIDATE_SCHEMA = "candidate_schema"
    EVIDENCE_GROUNDING = "evidence_grounding"


class RunPhase(StrEnum):
    """Phases enforced by callbacks and the bounded recovery loop."""

    INIT = "init"
    DISCOVER = "discover"
    GROUND = "ground"
    VALIDATE = "validate"
    REPAIR = "repair"
    DONE = "done"
    PARTIAL_OR_FAILED = "partial_or_failed"


@dataclass(frozen=True, slots=True)
class ToolIssue:
    """A Secret-safe issue that tells the model what failed and whether to retry."""

    code: ToolErrorCode
    category: str
    message: str
    field_path: str | None = None
    retryable: bool = False


@dataclass(slots=True)
class RunControlLedger:
    """Mutable run-control state, separate from accepted analysis state."""

    phase: RunPhase = RunPhase.INIT
    protocol_issue: ToolIssue | None = None
    retry_counts: dict[ToolErrorCode, int] = field(default_factory=dict)
    blocked_signatures: set[str] = field(default_factory=set)
    last_candidate_hash: str | None = None


def success_envelope(
    data: Any,
    *,
    meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Wrap a successful Tool observation in the one public result shape."""

    return {
        "ok": True,
        "data": data,
        "error": None,
        "meta": dict(meta or {}),
    }


def error_envelope(
    issue: ToolIssue,
    *,
    allowed_next_actions: Sequence[str] = (),
    meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Wrap a Tool issue without inventing HTTP status semantics."""

    return {
        "ok": False,
        "data": None,
        "error": {
            "code": issue.code.value,
            "category": issue.category,
            "message": issue.message,
            "field_path": issue.field_path,
            "retryable": issue.retryable,
            "allowed_next_actions": list(allowed_next_actions),
        },
        "meta": dict(meta or {}),
    }
