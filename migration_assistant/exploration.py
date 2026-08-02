"""Bounded, tool-using exploration orchestration for the migration agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Protocol

from .repository_tools import PUBLIC_TOOL_NAMES, RepositoryToolError, RepositoryTools, redact_sensitive_value


class ExplorationStatus(StrEnum):
    PARTIAL = "partial"
    COMPLETE = "complete"


class EvidenceStatus(StrEnum):
    CONFIRMED = "confirmed"
    INFERRED = "inferred"
    UNRESOLVED = "unresolved"
    CONFLICTING = "conflicting"


@dataclass(frozen=True)
class EvidenceRecord:
    status: str
    path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    text: str | None = None
    claim: str | None = None
    excerpt: str | None = None
    absence_scope: str | None = None
    absence_pattern: str | None = None


@dataclass
class ExplorationResult:
    status: ExplorationStatus
    iterations: int
    evidence: list[EvidenceRecord] = field(default_factory=list)
    observations: list[object] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class Planner(Protocol):
    def next_action(self, observation: object) -> Mapping[str, object]:
        """Select the next observation action or stop."""


class ExplorationLoop:
    """Run a planner against only the eight observation tools."""

    def __init__(self, repository_tools: RepositoryTools, planner: Planner, max_iterations: int = 10) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations는 1 이상이어야 합니다.")
        self.repository_tools = repository_tools
        self.planner = planner
        self.max_iterations = max_iterations

    def run(self, initial_observation: object | None = None) -> ExplorationResult:
        result = ExplorationResult(ExplorationStatus.PARTIAL, 0)
        observation = initial_observation
        for _ in range(self.max_iterations):
            result.iterations += 1
            try:
                action = self.planner.next_action(observation)
            except StopIteration:
                result.errors.append("planner가 다음 탐색 action을 제공하지 않았습니다.")
                return result
            if not isinstance(action, Mapping):
                result.errors.append("planner action은 mapping이어야 합니다.")
                return result
            if action.get("stop") is True:
                result.status = ExplorationStatus.COMPLETE
                return result
            tool_name = action.get("tool")
            if not isinstance(tool_name, str) or tool_name not in PUBLIC_TOOL_NAMES:
                result.errors.append("공개되지 않은 Repository Tool입니다.")
                return result
            try:
                method = getattr(self.repository_tools, tool_name)
                args = action.get("args", {})
                if not isinstance(args, Mapping):
                    raise RepositoryToolError("tool args는 mapping이어야 합니다.")
                observation = method(**dict(args))
                safe_observation = redact_sensitive_value(observation)
                result.observations.append(safe_observation)
                requested_status = action.get("status")
                self._record_evidence(result, observation, requested_status if isinstance(requested_status, str) else None)
            except (RepositoryToolError, TypeError, ValueError) as error:
                result.errors.append(str(redact_sensitive_value(str(error))))
                return result
        result.errors.append("최대 exploration iteration에 도달했습니다.")
        return result

    def _record_evidence(self, result: ExplorationResult, observation: object, status: str | None) -> None:
        if status not in {item.value for item in EvidenceStatus}:
            return
        safe_status = status
        if isinstance(observation, Mapping) and isinstance(observation.get("hits"), list):
            values = observation["hits"]
        else:
            values = observation if isinstance(observation, list) else [observation]
        for value in values:
            if not isinstance(value, Mapping):
                continue
            path = value.get("path")
            start = value.get("line_start")
            end = value.get("line_end")
            if isinstance(path, str) and isinstance(start, int) and isinstance(end, int):
                result.evidence.append(
                    EvidenceRecord(
                        status=safe_status,
                        path=path,
                        line_start=start,
                        line_end=end,
                        text=redact_sensitive_value(value.get("text")) if isinstance(value.get("text"), str) else None,
                        claim=redact_sensitive_value(value.get("claim")) if isinstance(value.get("claim"), str) else None,
                        excerpt=redact_sensitive_value(value.get("excerpt")) if isinstance(value.get("excerpt"), str) else None,
                    )
                )
            elif safe_status == EvidenceStatus.UNRESOLVED.value:
                result.evidence.append(
                    EvidenceRecord(
                        status=safe_status,
                        absence_scope=str(value.get("scope", ".")),
                        absence_pattern=str(value.get("pattern", "")),
                    )
                )
