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


class RecoveryDisposition(StrEnum):
    """Private runner decisions for a protocol issue.

    These values are deliberately not part of the model-facing envelope.  They
    describe whether the next model function call may consume the issue's
    correction lease or whether the runner must start/stop a bounded turn.
    """

    INLINE_CORRECTION = "inline_correction"
    INLINE_VALIDATE_ONLY = "inline_validate_only"
    NEXT_TURN_RECOVERY = "next_turn_recovery"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class ToolIssue:
    """A Secret-safe issue that tells the model what failed and whether to retry."""

    code: ToolErrorCode
    category: str
    message: str
    field_path: str | None = None
    retryable: bool = False
    # Measurement only. Deliberately absent from error_envelope: the model-facing
    # contract must not widen just because a run is being diagnosed.
    rejected_input: str | None = None


@dataclass(slots=True)
class RunControlLedger:
    """Mutable run-control state, separate from accepted analysis state."""

    phase: RunPhase = RunPhase.INIT
    protocol_issue: ToolIssue | None = None
    retry_counts: dict[ToolErrorCode, int] = field(default_factory=dict)
    blocked_signatures: set[str] = field(default_factory=set)
    last_candidate_hash: str | None = None
    candidate_hashes: set[str] = field(default_factory=set)
    attempted_actions: set[tuple[ToolErrorCode, str]] = field(default_factory=set)
    recovery_attempts: int = 0
    max_recovery_attempts: int = 1
    next_actions: tuple[str, ...] | None = None
    pending_originating_tool: str | None = None
    pending_call_id: str | None = None
    follow_up_actions: tuple[str, ...] = ()
    inline_lease_used: bool = False
    next_turn_lease_used: bool = False
    stop_requested: bool = False
    inline_corrections: int = 0
    max_inline_corrections: int = 3
    validation_attempts: int = 0
    max_validation_attempts: int = 2
    prebinding_rejections: int = 0
    max_prebinding_rejections: int = 1
    max_no_progress_seen: int = 0
    audit_issues: list[ToolIssue] = field(default_factory=list)
    _issue_fingerprints: set[str] = field(default_factory=set, repr=False)

    def record_issue(
        self,
        issue: ToolIssue,
        *,
        blocked_signature: str | None = None,
        allowed_next_actions: Sequence[str] = (),
        follow_up_actions: Sequence[str] = (),
        originating_tool: str | None = None,
        call_id: str | None = None,
    ) -> None:
        fingerprint = self.issue_fingerprint(issue, originating_tool, allowed_next_actions)
        if fingerprint in self._issue_fingerprints:
            self.stop_requested = True
        else:
            self._issue_fingerprints.add(fingerprint)
        if self.protocol_issue is None:
            # A completed correction starts a fresh issue lease.  A grounding
            # correction intentionally keeps the pending issue until its
            # follow-up validation call has been accepted.
            self.inline_lease_used = False
        self.protocol_issue = issue
        self.phase = RunPhase.REPAIR
        self.retry_counts[issue.code] = self.retry_counts.get(issue.code, 0) + 1
        self.next_actions = tuple(allowed_next_actions)
        self.follow_up_actions = tuple(follow_up_actions)
        self.pending_originating_tool = originating_tool
        self.pending_call_id = call_id
        if blocked_signature:
            self.blocked_signatures.add(blocked_signature)

    @staticmethod
    def issue_fingerprint(
        issue: ToolIssue,
        originating_tool: str | None = None,
        allowed_next_actions: Sequence[str] = (),
    ) -> str:
        """Return a Secret-safe issue identity for bounded repetition checks."""

        return "|".join(
            (
                issue.code.value,
                issue.category,
                issue.field_path or "",
                originating_tool or "",
                ",".join(allowed_next_actions),
            )
        )

    def mark_prebinding_rejection(self, issue: ToolIssue, originating_tool: str | None = None) -> bool:
        """Record an ADK/schema rejection before the handler is entered.

        The boolean indicates whether this fingerprint may be exposed to one
        correction.  No argument value is retained.
        """

        actions = (originating_tool,) if originating_tool else ("validate_analysis",)
        fingerprint = self.issue_fingerprint(issue, originating_tool, actions)
        if fingerprint in self._issue_fingerprints:
            self.stop_requested = True
            return False
        self.prebinding_rejections += 1
        if self.prebinding_rejections > self.max_prebinding_rejections:
            self.stop_requested = True
            return False
        return True

    def preserve_protocol_issue_for_audit(self) -> None:
        """Keep the active issue when a forbidden recovery action is rejected."""

        if self.protocol_issue is not None and (
            not self.audit_issues or self.audit_issues[-1] != self.protocol_issue
        ):
            self.audit_issues.append(self.protocol_issue)

    def authorize_action(
        self,
        action: str,
        phase_actions: Sequence[str],
    ) -> RecoveryDisposition:
        """Decide whether a model function call may execute.

        This is the single lease decision point used by the callbacks.  The
        action is checked only after the caller has performed duplicate and
        argument checks, so a rejected correction never consumes a lease.
        """

        if self.stop_requested or self.phase in {RunPhase.DONE, RunPhase.PARTIAL_OR_FAILED}:
            return RecoveryDisposition.STOP
        issue = self.protocol_issue
        if issue is None:
            if action in phase_actions:
                return RecoveryDisposition.INLINE_VALIDATE_ONLY
            return RecoveryDisposition.STOP
        allowed = self.allowed_next_actions(phase_actions)
        if action not in allowed:
            self.stop_requested = True
            return RecoveryDisposition.STOP
        if action in self.follow_up_actions:
            return RecoveryDisposition.INLINE_VALIDATE_ONLY
        if self.inline_lease_used or self.inline_corrections >= self.max_inline_corrections:
            self.stop_requested = True
            return RecoveryDisposition.STOP
        self.inline_lease_used = True
        self.inline_corrections += 1
        return RecoveryDisposition.INLINE_CORRECTION

    def complete_action(self, action: str) -> None:
        """Advance a pending correction after the Tool actually succeeded."""

        if self.protocol_issue is None:
            return
        if action in self.follow_up_actions:
            self.protocol_issue = None
            self.next_actions = None
            self.follow_up_actions = ()
            self.pending_originating_tool = None
            self.pending_call_id = None
            return
        if self.follow_up_actions:
            self.next_actions = self.follow_up_actions
            self.phase = RunPhase.REPAIR
            return
        self.protocol_issue = None
        self.next_actions = None
        self.follow_up_actions = ()
        self.pending_originating_tool = None
        self.pending_call_id = None

    def begin_next_turn(self) -> bool:
        """Consume the only recovery turn not covered by an inline lease."""

        if (
            self.stop_requested
            or self.next_turn_lease_used
            or self.inline_lease_used
            or self.recovery_attempts >= self.max_recovery_attempts
        ):
            self.stop_requested = True
            return False
        self.next_turn_lease_used = True
        self.recovery_attempts += 1
        return True

    def observe_no_progress(self, value: int) -> None:
        self.max_no_progress_seen = max(self.max_no_progress_seen, max(0, int(value)))

    def candidate_repeated(self, candidate: Mapping[str, Any]) -> bool:
        canonical = json.dumps(candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
        fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        repeated = fingerprint in self.candidate_hashes
        self.candidate_hashes.add(fingerprint)
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
        if self.stop_requested:
            return ()
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
