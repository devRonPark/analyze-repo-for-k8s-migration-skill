"""Provider-neutral protocol types shared by Agent Tool boundaries."""

from __future__ import annotations

import hashlib
import json
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
    attempted_actions: set[tuple[ToolErrorCode, str]] = field(default_factory=set)
    recovery_attempts: int = 0
    max_recovery_attempts: int = 2
    next_actions: tuple[str, ...] | None = None

    def record_issue(
        self,
        issue: ToolIssue,
        *,
        blocked_signature: str | None = None,
        allowed_next_actions: Sequence[str] = (),
    ) -> None:
        self.protocol_issue = issue
        self.phase = RunPhase.REPAIR
        self.retry_counts[issue.code] = self.retry_counts.get(issue.code, 0) + 1
        self.next_actions = tuple(allowed_next_actions)
        if blocked_signature:
            self.blocked_signatures.add(blocked_signature)

    def candidate_repeated(self, candidate: Mapping[str, Any]) -> bool:
        canonical = json.dumps(candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
        fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        repeated = fingerprint == self.last_candidate_hash
        self.last_candidate_hash = fingerprint
        return repeated

    def action_repeated(self, code: ToolErrorCode, action_fingerprint: str) -> bool:
        key = (code, action_fingerprint)
        if key in self.attempted_actions:
            return True
        self.attempted_actions.add(key)
        return False

    def allowed_next_actions(self, registered_names: Sequence[str]) -> tuple[str, ...]:
        registered = tuple(registered_names)
        issue = self.protocol_issue
        if self.phase in {RunPhase.DONE, RunPhase.PARTIAL_OR_FAILED}:
            return ()
        if issue is None:
            return registered
        if self.next_actions is not None:
            return tuple(name for name in self.next_actions if name in registered)
        if issue.code in {
            ToolErrorCode.CANDIDATE_SCHEMA,
            ToolErrorCode.EVIDENCE_GROUNDING,
            ToolErrorCode.BUDGET_EXHAUSTED,
        }:
            return ("validate_analysis",) if "validate_analysis" in registered else ()
        if issue.code == ToolErrorCode.FORBIDDEN_PATH:
            return tuple(name for name in registered if name != "inspect_target")
        return registered


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
