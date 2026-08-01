"""Google ADK function tools backed by the read-only RepositoryTools boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from .repository_tools import RepositoryToolError, RepositoryTools
from .target import BudgetExceededError, SafetyBudget


@dataclass
class DuplicateTracker:
    signatures: set[str] = field(default_factory=set)
    consecutive_no_progress: int = 0
    max_no_progress: int = 3

    def begin(self, tool_name: str, args: Mapping[str, object]) -> dict[str, object] | None:
        signature = json.dumps([tool_name, dict(args)], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if signature in self.signatures:
            self.consecutive_no_progress += 1
            return {
                "tool_name": tool_name,
                "normalized_args": dict(args),
                "valid": False,
                "duplicate": True,
                "no_progress": self.consecutive_no_progress,
                "error": "동일 Tool과 args 호출이 차단되었습니다. 이 호출을 반복하지 말고 다른 탐색 행동 또는 최종 분석을 선택하세요.",
            }
        self.signatures.add(signature)
        self.consecutive_no_progress = 0
        return None


@dataclass
class ValidationLedger:
    result: Any | None = None
    validation_error: str | None = None
    budget_exhausted: str | None = None
    tool_error: str | None = None
    observations: list[dict[str, object]] = field(default_factory=list)


class AdkRepositoryToolset:
    """Expose exactly eight functions to one ADK Agent."""

    def __init__(self, repository_tools: RepositoryTools, ledger: ValidationLedger, tracker: DuplicateTracker) -> None:
        self.repository_tools = repository_tools
        self.ledger = ledger
        self.tracker = tracker

    def _call(self, name: str, args: Mapping[str, object], operation: Any) -> object:
        duplicate = self.tracker.begin(name, args)
        if duplicate is not None:
            return duplicate
        try:
            result = operation()
            if name == "search_text" and isinstance(result, Mapping):
                hits = result.get("hits")
                if isinstance(hits, list):
                    self.ledger.observations.extend(
                        item for item in hits if isinstance(item, Mapping) and item.get("path")
                    )
            elif name == "read_file_lines" and isinstance(result, list):
                self.ledger.observations.extend(
                    item for item in result if isinstance(item, Mapping) and item.get("path")
                )
            if len(self.ledger.observations) > 64:
                del self.ledger.observations[:-64]
            return result
        except (BudgetExceededError, RepositoryToolError, TypeError, ValueError) as error:
            if isinstance(error, BudgetExceededError):
                self.ledger.budget_exhausted = str(error)
            else:
                self.ledger.tool_error = str(error)
            return {
                "valid": False,
                "budget_exhausted": isinstance(error, BudgetExceededError),
                "error": str(error),
                "next_action": "오류를 반복하지 말고 다른 유효한 Repository 탐색 또는 AnalysisResult 제출을 선택하세요.",
            }

    def inspect_target(self) -> dict[str, object]:
        """Inspect the local Git Repository safety boundary. This is not application evidence."""
        return self._call("inspect_target", {}, self.repository_tools.inspect_target)  # type: ignore[return-value]

    def list_tree(self, relative: str = ".", max_depth: int | None = None) -> object:
        """List Repository-relative files; .git is forbidden, while .gitignore and .github are allowed."""
        return self._call("list_tree", {"relative": relative, "max_depth": max_depth}, lambda: self.repository_tools.list_tree(relative, max_depth))

    def find_files(self, pattern: str) -> object:
        """Find bounded Repository-relative file candidates; never search inside the .git directory."""
        return self._call("find_files", {"pattern": pattern}, lambda: self.repository_tools.find_files(pattern))

    def search_text(self, pattern: str, relative: str = ".") -> object:
        """Search bounded text hits; .git is forbidden and every hit has path and line metadata."""
        return self._call("search_text", {"pattern": pattern, "relative": relative}, lambda: self.repository_tools.search_text(pattern, relative))

    def read_file(self, relative: str) -> object:
        """Read one bounded Repository-relative file; .git internals are forbidden and code is never executed."""
        return self._call("read_file", {"relative": relative}, lambda: self.repository_tools.read_file(relative))

    def read_file_lines(self, relative: str, line_start: int, line_end: int) -> object:
        """Read line-backed evidence; .git internals are forbidden and the range must exist."""
        args = {"relative": relative, "line_start": line_start, "line_end": line_end}
        return self._call("read_file_lines", args, lambda: self.repository_tools.read_file_lines(relative, line_start, line_end))

    def inspect_git_metadata(self) -> object:
        """Read restricted Git metadata only; never read .git files."""
        return self._call("inspect_git_metadata", {}, self.repository_tools.inspect_git_metadata)

    def validate_analysis(
        self,
        status: str,
        summary: str,
        evidence: list[dict],
        iterations: int,
        errors: list[str],
    ) -> dict[str, object]:
        """Validate the full candidate before termination.

        Pass the complete candidate as these five required fields. Each evidence item
        must contain status; positive items require repository-relative path,
        line_start and line_end. Unresolved items require absence_scope,
        absence_pattern and result. Extra fields are rejected by Pydantic. A
        partial candidate must include a non-empty errors list describing the
        genuine unresolved repository ambiguity; an empty list is invalid.
        """
        candidate = {
            "status": status,
            "summary": summary,
            "evidence": evidence,
            "iterations": iterations,
            "errors": errors,
        }
        preliminary = self._call("validate_analysis", candidate, lambda: self.repository_tools.validate_analysis(candidate))
        if not isinstance(preliminary, Mapping) or preliminary.get("valid") is not True:
            self.ledger.validation_error = "Repository evidence validation failed."
            response = dict(preliminary) if isinstance(preliminary, Mapping) else {"valid": False, "errors": ["invalid validation response"]}
            response["next_action"] = "오류를 수정한 전체 AnalysisResult candidate를 다시 validate_analysis에 전달하세요."
            return response
        from .analysis import AnalysisResult, PydanticDependencyError

        try:
            result = AnalysisResult.model_validate(candidate)
        except (ValueError, PydanticDependencyError) as error:
            self.ledger.validation_error = str(error)
            return {"valid": False, "errors": [str(error)]}
        if result.status == "complete":
            positive = [item for item in result.evidence if item.path and item.line_start and item.line_end]
            if not result.evidence or not positive:
                self.ledger.validation_error = "complete 결과에는 line-backed evidence가 필요합니다."
                return {
                    "valid": False,
                    "errors": [self.ledger.validation_error],
                    "next_action": "line-backed positive evidence를 추가한 전체 candidate를 다시 제출하세요.",
                }
        self.ledger.result = result
        self.ledger.validation_error = None
        return {"valid": True, "analysis": result.model_dump(mode="json")}

    def functions(self) -> list[object]:
        return [
            self.inspect_target,
            self.list_tree,
            self.find_files,
            self.search_text,
            self.read_file,
            self.read_file_lines,
            self.inspect_git_metadata,
            self.validate_analysis,
        ]
