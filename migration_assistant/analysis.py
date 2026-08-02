"""Strict, repository-grounded analysis result and application service."""

from __future__ import annotations

import json
import os
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from .adapter import AdapterConfigurationError
from .config import Settings
from .exploration import EvidenceStatus, ExplorationLoop, ExplorationStatus, Planner
from .repository_tools import RepositoryTools, redact_sensitive_value
from .target import SafetyBudget, TargetSafetyGate

try:
    from pydantic import BaseModel, ConfigDict, Field, model_validator

    PYDANTIC_AVAILABLE = True
except ModuleNotFoundError:
    BaseModel = None  # type: ignore[assignment,misc]
    PYDANTIC_AVAILABLE = False


class AnalysisStatus(StrEnum):
    PARTIAL = "partial"
    FAILED = "failed"
    COMPLETE = "complete"


class PydanticDependencyError(RuntimeError):
    """Raised when the required runtime schema dependency is unavailable."""


def _meaningful(value: object) -> bool:
    return isinstance(value, str) and value.strip().casefold() not in {"", "n/a", "na", "unknown", "placeholder", "todo", "tbd"}


def _existence_only_claim(value: str) -> bool:
    return " ".join(value.casefold().split()) in {
        "file exists", "path exists", "파일이 존재한다", "파일이 존재함", "파일 존재"
    }


def _validate_evidence(data: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise ValueError("evidence must be an object")
    allowed = {
        "id", "status", "path", "line_start", "line_end", "claim", "text", "excerpt",
        "absence_scope", "absence_pattern", "result",
    }
    extra = set(data) - allowed
    if extra:
        raise ValueError(f"evidence extra field: {sorted(extra)}")
    normalized = dict(redact_sensitive_value(dict(data)))
    status = normalized.get("status")
    if status not in {item.value for item in EvidenceStatus}:
        raise ValueError("evidence status가 올바르지 않습니다.")
    if status == EvidenceStatus.UNRESOLVED.value:
        if not all(_meaningful(normalized.get(key)) for key in ("absence_scope", "absence_pattern", "result")):
            raise ValueError("unresolved evidence에는 absence scope, pattern, result가 필요합니다.")
    else:
        path = normalized.get("path")
        start = normalized.get("line_start")
        end = normalized.get("line_end")
        if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
            raise ValueError("positive evidence에는 repository-relative path가 필요합니다.")
        if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
            raise ValueError("evidence line 범위가 올바르지 않습니다.")
    if normalized.get("excerpt") is None and isinstance(normalized.get("text"), str):
        normalized["excerpt"] = normalized["text"]
    if normalized.get("text") is None and isinstance(normalized.get("excerpt"), str):
        normalized["text"] = normalized["excerpt"]
    return normalized


if PYDANTIC_AVAILABLE:

    class Evidence(BaseModel):
        model_config = ConfigDict(extra="forbid")

        id: str | None = None
        status: str
        path: str | None = None
        line_start: int | None = None
        line_end: int | None = None
        claim: str | None = None
        text: str | None = None
        excerpt: str | None = None
        absence_scope: str | None = None
        absence_pattern: str | None = None
        result: str | None = None

        @model_validator(mode="before")
        @classmethod
        def validate_raw(cls, value: Any) -> Any:
            return _validate_evidence(value)


    class Finding(BaseModel):
        model_config = ConfigDict(extra="forbid")

        id: str
        status: str
        claim: str
        summary: str | None = None
        evidence_ids: list[str] = Field(default_factory=list)
        resolution_owner: str | None = None
        resolution_source: str | None = None
        reason: str | None = None

        @model_validator(mode="before")
        @classmethod
        def redact_raw(cls, value: Any) -> Any:
            return redact_sensitive_value(value)


    class AnalysisResult(BaseModel):
        model_config = ConfigDict(extra="forbid")

        status: str
        summary: str
        evidence: list[Evidence] = Field(default_factory=list)
        findings: list[Finding] = Field(default_factory=list)
        iterations: int = 0
        errors: list[str] = Field(default_factory=list)
        termination: str = "normal"

        @model_validator(mode="before")
        @classmethod
        def redact_raw(cls, value: Any) -> Any:
            return redact_sensitive_value(value) if isinstance(value, Mapping) else value

        @model_validator(mode="after")
        def validate_status(self) -> "AnalysisResult":
            if self.status not in {item.value for item in AnalysisStatus}:
                raise ValueError("analysis status가 올바르지 않습니다.")
            evidence_ids = {item.id for item in self.evidence if item.id}
            if len(evidence_ids) != sum(item.id is not None for item in self.evidence):
                raise ValueError("evidence id는 고유해야 합니다.")
            finding_ids = {item.id for item in self.findings}
            if len(finding_ids) != len(self.findings):
                raise ValueError("finding id는 고유해야 합니다.")
            for finding in self.findings:
                if finding.status not in {item.value for item in EvidenceStatus}:
                    raise ValueError("finding status가 올바르지 않습니다.")
                if finding.status == EvidenceStatus.UNRESOLVED.value:
                    if finding.resolution_owner not in {"repository", "user", "deployment_environment", "external_system"}:
                        raise ValueError("unresolved finding에는 resolution_owner가 필요합니다.")
                    if not _meaningful(finding.resolution_source) or not _meaningful(finding.reason):
                        raise ValueError("unresolved finding에는 resolution_source와 reason이 필요합니다.")
                elif not finding.evidence_ids or any(item not in evidence_ids for item in finding.evidence_ids):
                    raise ValueError("positive finding은 Evidence ID를 참조해야 합니다.")
            positive = [item for item in self.evidence if item.status != EvidenceStatus.UNRESOLVED.value]
            grounded_positive = [
                item for item in positive
                if _meaningful(item.claim)
                and not _existence_only_claim(item.claim or "")
                and _meaningful(item.excerpt or item.text)
                and bool(item.path)
                and bool(item.line_start)
                and bool(item.line_end)
            ]
            if self.status == AnalysisStatus.COMPLETE.value:
                if self.errors:
                    raise ValueError("complete 결과에는 errors를 남길 수 없습니다.")
                if not self.findings:
                    raise ValueError("complete 결과에는 structured finding이 필요합니다.")
                if not positive or any(
                    not item.id or not _meaningful(item.claim) or _existence_only_claim(item.claim or "")
                    or not _meaningful(item.excerpt or item.text)
                    or not item.path or not item.line_start or not item.line_end
                    for item in positive
                ):
                    raise ValueError("complete 결과에는 검증 가능한 line-backed Evidence가 필요합니다.")
            if self.status == AnalysisStatus.PARTIAL.value:
                if not self.errors:
                    raise ValueError("partial 결과에는 partial 사유가 errors에 필요합니다.")
                if not grounded_positive:
                    raise ValueError("partial 결과에는 최소 하나의 positive line-backed Evidence가 필요합니다.")
            return self

else:

    class Evidence:
        @classmethod
        def model_validate(cls, value: object) -> "Evidence":
            raise PydanticDependencyError("필수 dependency pydantic이 설치되지 않아 AnalysisResult를 검증할 수 없습니다.")


    class Finding:
        @classmethod
        def model_validate(cls, value: object) -> "Finding":
            raise PydanticDependencyError("필수 dependency pydantic이 설치되지 않아 AnalysisResult를 검증할 수 없습니다.")


    class AnalysisResult:
        @classmethod
        def model_validate(cls, value: object) -> "AnalysisResult":
            raise PydanticDependencyError("필수 dependency pydantic이 설치되지 않아 AnalysisResult를 검증할 수 없습니다.")


def require_pydantic() -> None:
    if not PYDANTIC_AVAILABLE:
        raise PydanticDependencyError("필수 dependency pydantic이 설치되지 않아 분석을 시작할 수 없습니다.")


def _result_to_dict(result: AnalysisResult) -> dict[str, Any]:
    data = result.model_dump(mode="json") if PYDANTIC_AVAILABLE else result.model_dump()  # type: ignore[call-arg]
    return json.loads(json.dumps(data, ensure_ascii=False))


def render_report(result: AnalysisResult) -> str:
    data = _result_to_dict(result)
    lines = ["# Repository 분석 보고서", "", f"상태: {data['status']}", "", redact_sensitive_value(data["summary"]), "", "## Findings"]
    for finding in data["findings"]:
        line = f"- {finding['id']} [{finding['status']}]: {finding['claim']}"
        if finding.get("evidence_ids"):
            line += f" (Evidence: {', '.join(finding['evidence_ids'])})"
        if finding.get("resolution_owner"):
            line += f" / owner={finding['resolution_owner']} source={finding.get('resolution_source')}"
        lines.append(redact_sensitive_value(line))
    lines.extend(["", "## 근거"])
    for item in data["evidence"]:
        if item.get("path"):
            location = f"{item['path']}:{item.get('line_start')}-{item.get('line_end')}"
            text = item.get("excerpt") or item.get("text") or ""
        else:
            location = f"검색(scope={item.get('absence_scope')}, pattern={item.get('absence_pattern')})"
            text = item.get("result") or ""
        lines.append(redact_sensitive_value(f"- {item['id'] or '-'} {item['status']}: {location} {text}".rstrip()))
    if data["errors"]:
        lines.extend(["", "## 오류", *[f"- {redact_sensitive_value(error)}" for error in data["errors"]]])
    return "\n".join(lines) + "\n"


class ModelConfigurationError(RuntimeError):
    """Raised when no approved live model profile is available."""


def analyze(
    repository: str | Path,
    output: str | Path | None,
    planner: Planner | None = None,
    *,
    max_iterations: int | None = None,
    adk_model: object | None = None,
    run_metadata: MutableMapping[str, object] | None = None,
) -> AnalysisResult:
    require_pydantic()
    budget = SafetyBudget(max_iterations=max_iterations if max_iterations is not None else SafetyBudget().max_iterations)
    if budget.max_iterations < 1 or budget.max_iterations > 1000:
        raise ValueError("max_iterations는 1 이상 1000 이하이어야 합니다.")
    gate = TargetSafetyGate.open(repository, output, budget=budget)
    transaction = gate.create_output()
    try:
        tools = RepositoryTools(gate.repository, budget=gate.budget)
        if planner is not None:
            explored = ExplorationLoop(tools, planner, max_iterations=budget.max_iterations).run()
            evidence = [item.__dict__ for item in explored.evidence]
            result_status = AnalysisStatus.PARTIAL.value if explored.status == ExplorationStatus.PARTIAL else AnalysisStatus.FAILED.value
            result_errors = list(explored.errors)
            if explored.status == ExplorationStatus.COMPLETE:
                result_errors.append("Python planner fallback은 Agent의 structured finding을 대신할 수 없어 complete로 승격되지 않습니다.")
            positive = [item for item in evidence if item.get("path") and item.get("line_start") and item.get("line_end")]
            if not positive:
                result_status = AnalysisStatus.FAILED.value
                result_errors.append("확인 가능한 line-backed Repository 근거가 없어 결과를 complete로 기록할 수 없습니다.")
            elif result_status == AnalysisStatus.PARTIAL.value:
                result_status = AnalysisStatus.FAILED.value
                result_errors.append("Python planner fallback 관찰은 Agent의 structured finding을 대신할 수 없어 보고 가능한 Evidence로 승격되지 않으므로 partial로 기록할 수 없습니다.")
            result = AnalysisResult.model_validate({
                "status": result_status,
                "summary": "Repository 탐색이 완료되었습니다." if result_status == ExplorationStatus.COMPLETE.value else "Repository 탐색이 부분 완료되었습니다.",
                # Planner fallback observations are never promoted into reportable Evidence.
                "evidence": [],
                "findings": [],
                "iterations": explored.iterations,
                "errors": result_errors,
                "termination": "planner_fallback",
            })
        else:
            if adk_model is None:
                missing = [name for name in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_TIMEOUT_SECONDS", "LLM_MAX_TOKENS") if not os.environ.get(name)]
                if missing:
                    raise ModelConfigurationError(f"live model profile 설정이 없습니다: {', '.join(missing)}")
                try:
                    settings = Settings.from_environment()
                except (ValueError, AdapterConfigurationError) as error:
                    raise ModelConfigurationError(f"live model profile 설정이 올바르지 않습니다: {error}") from error
            else:
                settings = Settings()
            try:
                from .adk_runner import run_adk_agent
            except ModuleNotFoundError as error:
                if (error.name or "").startswith("google"):
                    from .agent import GoogleAdkDependencyError
                    raise GoogleAdkDependencyError("필수 dependency google-adk가 설치되지 않아 분석을 시작할 수 없습니다.") from error
                raise
            run = run_adk_agent(tools, settings, budget, model_override=adk_model)
            if run_metadata is not None:
                run_metadata.clear()
                run_metadata.update(
                    {
                        "terminal": bool(getattr(run, "terminal", False)),
                        "tool_calls": [str(name) for name in getattr(run, "tool_calls", [])],
                        "protocol_issues": redact_sensitive_value(
                            list(getattr(run, "protocol_issues", []))
                        ),
                        "recovery_attempts": int(getattr(run, "recovery_attempts", 0)),
                        "evidence_provenance": redact_sensitive_value(
                            list(getattr(run, "evidence_provenance", []))
                        ),
                        "provenance_summary": redact_sensitive_value(
                            dict(getattr(run, "provenance_summary", {}))
                        ),
                    }
                )
            result = run.result
            if result is None:
                raise RuntimeError("ADK Runner가 AnalysisResult를 반환하지 않았습니다.")
        (transaction.path / "analysis-result.json").write_text(json.dumps(_result_to_dict(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (transaction.path / "analysis-report.md").write_text(render_report(result), encoding="utf-8")
        transaction.mark_complete()
        return result
    except Exception:
        transaction.cleanup()
        raise
