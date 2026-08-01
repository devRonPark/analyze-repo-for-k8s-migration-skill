"""Strict analysis result contract and analysis-only application service."""

from __future__ import annotations

import json
import os
import re
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

from .adapter import AdapterConfigurationError
from .config import Settings
from .exploration import EvidenceStatus, ExplorationLoop, ExplorationStatus, Planner
from .repository_tools import RepositoryTools
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


_SECRET = re.compile(
    r"(?i)(\b(?:password|passwd|secret|token|api[_-]?key|private[_-]?key)\b\s*[:=]\s*)([^\s#;,]+)"
)


def _redact(value: str) -> str:
    return _SECRET.sub(r"\1<REDACTED>", value)


def _validate_evidence(data: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise ValueError("evidence must be an object")
    allowed = {"status", "path", "line_start", "line_end", "text", "absence_scope", "absence_pattern", "result"}
    extra = set(data) - allowed
    if extra:
        raise ValueError(f"evidence extra field: {sorted(extra)}")
    status = str(data.get("status", ""))
    if status not in {item.value for item in EvidenceStatus}:
        raise ValueError("evidence status가 올바르지 않습니다.")
    path = data.get("path")
    start = data.get("line_start")
    end = data.get("line_end")
    if status == EvidenceStatus.UNRESOLVED.value:
        if not all(isinstance(data.get(key), str) for key in ("absence_scope", "absence_pattern", "result")):
            raise ValueError("unresolved evidence에는 absence scope, pattern, result가 필요합니다.")
    else:
        if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
            raise ValueError("positive evidence에는 repository-relative path가 필요합니다.")
        if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
            raise ValueError("evidence line 범위가 올바르지 않습니다.")
    normalized = dict(data)
    if isinstance(normalized.get("text"), str):
        normalized["text"] = _redact(normalized["text"])
    return normalized


if PYDANTIC_AVAILABLE:

    class Evidence(BaseModel):
        model_config = ConfigDict(extra="forbid")

        status: str
        path: str | None = None
        line_start: int | None = None
        line_end: int | None = None
        text: str | None = None
        absence_scope: str | None = None
        absence_pattern: str | None = None
        result: str | None = None

        @model_validator(mode="before")
        @classmethod
        def validate_raw(cls, value: Any) -> Any:
            return _validate_evidence(value)

    class AnalysisResult(BaseModel):
        model_config = ConfigDict(extra="forbid")

        status: str
        summary: str
        evidence: list[Evidence] = Field(default_factory=list)
        iterations: int = 0
        errors: list[str] = Field(default_factory=list)

        @model_validator(mode="before")
        @classmethod
        def redact_raw(cls, value: Any) -> Any:
            if not isinstance(value, Mapping):
                return value
            normalized = dict(value)
            if isinstance(normalized.get("summary"), str):
                normalized["summary"] = _redact(normalized["summary"])
            if isinstance(normalized.get("errors"), list):
                normalized["errors"] = [_redact(item) if isinstance(item, str) else item for item in normalized["errors"]]
            return normalized

        @model_validator(mode="after")
        def validate_status(self) -> "AnalysisResult":
            if self.status not in {item.value for item in AnalysisStatus}:
                raise ValueError("analysis status가 올바르지 않습니다.")
            if self.status == AnalysisStatus.COMPLETE.value:
                positive = [item for item in self.evidence if item.path and item.line_start and item.line_end]
                if not self.evidence or not positive:
                    raise ValueError("complete 결과에는 line-backed evidence가 필요합니다.")
            if self.status == AnalysisStatus.PARTIAL.value and not self.errors:
                raise ValueError("partial 결과에는 partial 사유가 errors에 필요합니다.")
            if self.status == AnalysisStatus.PARTIAL.value:
                positive = [item for item in self.evidence if item.path and item.line_start and item.line_end]
                if not positive:
                    raise ValueError("partial 결과에도 최소 하나의 line-backed evidence가 필요합니다.")
            return self

else:

    class Evidence:
        """Unavailable placeholder that cannot validate or serialize successfully."""

        @classmethod
        def model_validate(cls, value: object) -> "Evidence":
            raise PydanticDependencyError(
                "필수 dependency pydantic이 설치되지 않아 AnalysisResult를 검증할 수 없습니다."
            )

    class AnalysisResult:
        """Unavailable placeholder that fails closed instead of validating locally."""

        @classmethod
        def model_validate(cls, value: object) -> "AnalysisResult":
            raise PydanticDependencyError(
                "필수 dependency pydantic이 설치되지 않아 AnalysisResult를 검증할 수 없습니다."
            )


def require_pydantic() -> None:
    if not PYDANTIC_AVAILABLE:
        raise PydanticDependencyError(
            "필수 dependency pydantic이 설치되지 않아 분석을 시작할 수 없습니다."
        )


def _result_to_dict(result: AnalysisResult) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        data = result.model_dump(mode="json") if PYDANTIC_AVAILABLE else result.model_dump()  # type: ignore[call-arg]
    else:
        data = result.dict()
    return json.loads(json.dumps(data, ensure_ascii=False))


def render_report(result: AnalysisResult) -> str:
    data = _result_to_dict(result)
    lines = ["# Repository 분석 보고서", "", f"상태: {data['status']}", "", data["summary"], "", "## 근거"]
    for item in data["evidence"]:
        if item.get("path"):
            location = f"{item['path']}:{item.get('line_start')}-{item.get('line_end')}"
            text = item.get("text") or ""
        else:
            location = f"검색(scope={item.get('absence_scope')}, pattern={item.get('absence_pattern')})"
            text = ""
        lines.append(f"- {item['status']}: {location} {text}".rstrip())
    if data["errors"]:
        lines.extend(["", "## 오류", *[f"- {_redact(error)}" for error in data["errors"]]])
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
            result_status = explored.status.value
            result_errors = list(explored.errors)
            positive = [item for item in evidence if item.get("path") and item.get("line_start") and item.get("line_end")]
            if not positive:
                result_status = AnalysisStatus.FAILED.value
                result_errors.append("확인 가능한 line-backed Repository 근거가 없어 partial/complete로 기록할 수 없습니다.")
            result = AnalysisResult.model_validate(
                {
                    "status": result_status,
                    "summary": "Repository 탐색이 완료되었습니다." if result_status == ExplorationStatus.COMPLETE.value else "Repository 탐색이 부분 완료되었습니다.",
                    "evidence": evidence,
                    "iterations": explored.iterations,
                    "errors": result_errors,
                }
            )
        else:
            if adk_model is None:
                missing = [
                    name
                    for name in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_TIMEOUT_SECONDS", "LLM_MAX_TOKENS")
                    if not os.environ.get(name)
                ]
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

                    raise GoogleAdkDependencyError(
                        "필수 dependency google-adk가 설치되지 않아 분석을 시작할 수 없습니다."
                    ) from error
                raise

            run = run_adk_agent(tools, settings, budget, model_override=adk_model)
            result = run.result
            if result is None:
                raise RuntimeError("ADK Runner가 AnalysisResult를 반환하지 않았습니다.")
        (transaction.path / "analysis-result.json").write_text(
            json.dumps(_result_to_dict(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (transaction.path / "analysis-report.md").write_text(render_report(result), encoding="utf-8")
        transaction.mark_complete()
        return result
    except Exception:
        transaction.cleanup()
        raise
