"""Google ADK function tools backed by the read-only RepositoryTools boundary."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from .repository_tools import RepositoryToolError, RepositoryTools, redact_sensitive_value
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
                "normalized_args": redact_sensitive_value(dict(args)),
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

    @staticmethod
    def _recovery_action(error: str) -> str:
        if ".git" in error:
            return ".git 호출은 재시도하지 말고, 이미 확보한 일반 Repository 관찰만 사용해 전체 candidate를 validate_analysis에 제출하세요."
        if "line evidence" in error:
            return "큰 line 범위는 재시도하지 말고, search_text hit의 짧은 범위만 사용해 전체 candidate를 validate_analysis에 제출하세요."
        if "line 범위" in error:
            return "존재가 확인된 짧은 line 범위만 사용하고 잘못된 호출은 재시도하지 말고 전체 candidate를 validate_analysis에 제출하세요."
        return "오류를 반복하지 말고 다른 유효한 Repository 탐색 또는 AnalysisResult candidate를 validate_analysis에 제출하세요."

    @staticmethod
    def _normalize_verified_candidate(
        candidate: Mapping[str, object],
        corrections: list[object],
    ) -> dict[str, object] | None:
        evidence_value = candidate.get("evidence")
        findings_value = candidate.get("findings")
        if not isinstance(evidence_value, list) or not isinstance(findings_value, list):
            return None
        evidence = [dict(item) for item in evidence_value if isinstance(item, Mapping)]
        findings = [dict(item) for item in findings_value if isinstance(item, Mapping)]
        changed = len(evidence) != len(evidence_value) or len(findings) != len(findings_value)
        status = candidate.get("status")
        if isinstance(status, str) and not status.strip():
            if candidate.get("errors"):
                normalized_status = "partial"
            else:
                normalized_status = "complete"
            candidate = {**candidate, "status": normalized_status}
            changed = True
        evidence_ids: set[str] = set()
        for index, item in enumerate(evidence, 1):
            evidence_id = item.get("id")
            if not isinstance(evidence_id, str) or not evidence_id.strip() or evidence_id in evidence_ids:
                generated = f"e{index}"
                while generated in evidence_ids:
                    generated = f"e{index + 1}"
                item["id"] = generated
                evidence_id = generated
                changed = True
            evidence_ids.add(evidence_id)

        correction_by_id = {
            item.get("id"): item
            for item in corrections
            if isinstance(item, Mapping) and isinstance(item.get("id"), str)
        }
        correction_by_index = {
            item.get("index"): item
            for item in corrections
            if isinstance(item, Mapping) and isinstance(item.get("index"), int)
        }
        for index, item in enumerate(evidence):
            correction = correction_by_id.get(item.get("id")) or correction_by_index.get(index)
            if not isinstance(correction, Mapping) or not isinstance(correction.get("excerpt"), str):
                continue
            item["text"] = correction["excerpt"]
            item["excerpt"] = correction["excerpt"]
            if isinstance(correction.get("line_end"), int):
                item["line_end"] = correction["line_end"]
            changed = True

        def normalized(value: object) -> str:
            return " ".join(str(value or "").casefold().split())

        for index, finding in enumerate(findings, 1):
            finding_id = finding.get("id")
            if not isinstance(finding_id, str) or not finding_id.strip() or finding_id in {item.get("id") for item in findings[:index - 1]}:
                finding["id"] = f"f{index}"
                changed = True
            if finding.get("status") == "unresolved":
                if finding.get("resolution_owner") not in {"repository", "user", "deployment_environment", "external_system"}:
                    finding["resolution_owner"] = "deployment_environment"
                    changed = True
                if not isinstance(finding.get("resolution_source"), str) or not finding["resolution_source"].strip():
                    finding["resolution_source"] = "deployment decision not determined by Repository"
                    changed = True
                if not isinstance(finding.get("reason"), str) or not finding["reason"].strip():
                    finding["reason"] = "Repository evidence is insufficient to choose this deployment setting."
                    changed = True
                continue
            refs = finding.get("evidence_ids")
            valid_refs = [ref for ref in refs if ref in evidence_ids] if isinstance(refs, list) else []
            if not valid_refs:
                claim = normalized(finding.get("claim"))
                valid_refs = [
                    item["id"]
                    for item in evidence
                    if item.get("status") != "unresolved"
                    and claim
                    and claim == normalized(item.get("claim"))
                ]
            if not valid_refs:
                claim_tokens = set(re.findall(r"[a-z0-9가-힣]{2,}", normalized(finding.get("claim"))))
                scored = [
                    (
                        len(claim_tokens & set(re.findall(r"[a-z0-9가-힣]{2,}", normalized(item.get("claim"))))),
                        item["id"],
                    )
                    for item in evidence
                    if item.get("status") != "unresolved"
                ]
                best_score = max((score for score, _ in scored), default=0)
                if best_score > 0:
                    valid_refs = [item_id for score, item_id in scored if score == best_score]
            if valid_refs and valid_refs != refs:
                finding["evidence_ids"] = valid_refs
                changed = True

        if not changed:
            return None
        return {**candidate, "evidence": evidence, "findings": findings}

    def _call(self, name: str, args: Mapping[str, object], operation: Any) -> object:
        duplicate = self.tracker.begin(name, args)
        if duplicate is not None:
            return duplicate
        try:
            result = operation()
            if name == "search_text" and isinstance(result, Mapping):
                hits = result.get("hits")
                if isinstance(hits, list):
                    self.ledger.observations.extend(redact_sensitive_value(item) for item in hits if isinstance(item, Mapping) and item.get("path"))
            elif name == "read_file_lines" and isinstance(result, list):
                self.ledger.observations.extend(redact_sensitive_value(item) for item in result if isinstance(item, Mapping) and item.get("path"))
            if len(self.ledger.observations) > 64:
                del self.ledger.observations[:-64]
            return redact_sensitive_value(result)
        except (BudgetExceededError, RepositoryToolError, TypeError, ValueError) as error:
            safe_error = str(redact_sensitive_value(str(error)))
            if isinstance(error, BudgetExceededError):
                self.ledger.budget_exhausted = safe_error
            else:
                self.ledger.tool_error = safe_error
            return {
                "valid": False,
                "budget_exhausted": isinstance(error, BudgetExceededError),
                "error": safe_error,
                "next_action": self._recovery_action(safe_error),
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
        """Read at most four lines of line-backed evidence; .git internals are forbidden and the range must exist."""
        args = {"relative": relative, "line_start": line_start, "line_end": line_end}
        return self._call("read_file_lines", args, lambda: self.repository_tools.read_file_lines(relative, line_start, line_end))

    def inspect_git_metadata(self) -> object:
        """Read restricted Git metadata only; never read .git files."""
        return self._call("inspect_git_metadata", {}, self.repository_tools.inspect_git_metadata)

    def validate_analysis(
        self,
        status: Literal["complete", "partial", "failed"],
        summary: str,
        evidence: list[dict],
        findings: list[dict],
        iterations: int,
        errors: list[str],
        termination: str = "normal",
    ) -> dict[str, object]:
        """Validate the full candidate before termination.

        Pass the complete candidate with these required fields. Each evidence item
        must contain status; positive items require repository-relative path,
        line_start and line_end. Unresolved items require absence_scope,
        absence_pattern and result. Extra fields are rejected by Pydantic. A
        partial candidate must include a non-empty errors list describing the
        genuine unresolved repository ambiguity; an empty list is invalid.
        """
        candidate = redact_sensitive_value({
            "status": status,
            "summary": summary,
            "evidence": evidence,
            "findings": findings,
            "iterations": iterations,
            "errors": errors,
            "termination": termination,
        })
        preliminary = self._call("validate_analysis", candidate, lambda: self.repository_tools.validate_analysis(candidate))
        normalized_errors: list[object] = []
        corrections = preliminary.get("evidence_corrections") if isinstance(preliminary, Mapping) else []
        corrected_candidate = self._normalize_verified_candidate(
            candidate,
            corrections if isinstance(corrections, list) else [],
        )
        if corrected_candidate is not None:
            corrected = self.repository_tools.validate_analysis(corrected_candidate)
            if corrected.get("valid") is True:
                candidate = corrected_candidate
                preliminary = corrected
            else:
                normalized_errors = list(corrected.get("errors", [])) if isinstance(corrected.get("errors"), list) else []
        if not isinstance(preliminary, Mapping) or preliminary.get("valid") is not True:
            response = dict(preliminary) if isinstance(preliminary, Mapping) else {"valid": False, "errors": ["invalid validation response"]}
            if normalized_errors:
                response["normalized_errors"] = normalized_errors
            details = response.get("errors")
            if isinstance(details, list) and details:
                safe_details = "; ".join(str(redact_sensitive_value(item)) for item in details[:8])
                self.ledger.validation_error = f"Repository evidence validation failed: {safe_details}"
            else:
                self.ledger.validation_error = "Repository evidence validation failed."
            response["next_action"] = "오류를 수정한 전체 AnalysisResult candidate를 다시 validate_analysis에 전달하세요."
            return response
        from .analysis import AnalysisResult, PydanticDependencyError

        try:
            result = AnalysisResult.model_validate(candidate)
        except (ValueError, PydanticDependencyError) as error:
            self.ledger.validation_error = str(error)
            return {
                "valid": False,
                "errors": [str(error)],
                "next_action": (
                    "전체 candidate를 다시 validate_analysis에 전달하세요. "
                    "top-level status는 complete, partial, failed 중 하나이며, "
                    "confirmed/inferred/unresolved/conflicting은 Evidence와 Finding의 status에만 사용합니다."
                ),
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
