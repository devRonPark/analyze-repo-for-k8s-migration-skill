"""Single Google ADK Runner execution boundary for repository analysis."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .adk_tools import AdkRepositoryToolset, DuplicateTracker, ValidationLedger
from .agent import AgentApplication
from .analysis import AnalysisResult, PydanticDependencyError
from .config import Settings
from .repository_tools import RepositoryTools, redact_sensitive_text
from .target import BudgetExceededError, SafetyBudget
from .tool_protocol import RunControlLedger


class AdkExecutionError(RuntimeError):
    """Raised for non-configuration ADK execution failures."""


@dataclass
class AdkRun:
    result: AnalysisResult | None = None
    errors: list[str] = field(default_factory=list)
    final_text: str = ""
    tool_calls: list[str] = field(default_factory=list)


_FENCED_JSON = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def parse_structured_final(text: str) -> dict[str, object] | None:
    candidate = text.strip()
    fenced = _FENCED_JSON.search(candidate)
    if fenced:
        candidate = fenced.group(1)
    try:
        value = json.loads(candidate)
        return dict(value) if isinstance(value, dict) else None
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, character in enumerate(candidate):
            if character != "{":
                continue
            try:
                value, _ = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
        return None


def run_adk_agent(
    repository: RepositoryTools,
    settings: Settings,
    budget: SafetyBudget,
    *,
    model_override: object | None = None,
) -> AdkRun:
    ledger = ValidationLedger()
    tracker = DuplicateTracker(max_no_progress=budget.max_no_progress)
    control = RunControlLedger()
    agent = AgentApplication(settings).build_root_agent(
        repository_tools=repository,
        ledger=ledger,
        tracker=tracker,
        budget=budget,
        model_override=model_override,
        control=control,
    )
    run = AdkRun()

    async def execute() -> None:
        session_service = InMemorySessionService()
        session = await session_service.create_session(app_name="kubernetes_migration_assistant", user_id="local-user")
        runner = Runner(
            agent=agent,
            app_name="kubernetes_migration_assistant",
            session_service=session_service,
        )
        message = types.Content(
            role="user",
            parts=[types.Part(text="Local Repository를 분석하고 Kubernetes 이관에 필요한 근거 기반 AnalysisResult를 작성하세요.")],
        )
        async def consume(events: Any) -> None:
            try:
                while True:
                    try:
                        event = await events.__anext__()
                    except StopAsyncIteration:
                        break
                    run.tool_calls.extend(call.name for call in event.get_function_calls())
                    content = getattr(event, "content", None)
                    if content is not None and getattr(content, "role", None) == "model":
                        text = "\n".join(part.text for part in (content.parts or []) if getattr(part, "text", None))
                        if text:
                            run.final_text = redact_sensitive_text(text)
                    if ledger.result is not None:
                        await events.aclose()
                        break
                    # Let the model see validate_analysis's structured errors
                    # and correct the same candidate in the current turn. A
                    # repository/tool failure still ends the stream so the
                    # bounded recovery prompt can steer it safely.
                    if ledger.tool_error or ledger.budget_exhausted:
                        await events.aclose()
                        break
                    if tracker.consecutive_no_progress >= tracker.max_no_progress:
                        run.errors.append("동일 Tool 반복으로 no-progress 한도에 도달했습니다.")
                        await events.aclose()
                        break
            finally:
                if not getattr(events, "ag_closed", False):
                    await events.aclose()

        await consume(runner.run_async(user_id="local-user", session_id=session.id, new_message=message))
        if (
            ledger.result is None
            and tracker.consecutive_no_progress < tracker.max_no_progress
            and budget.iterations < budget.max_iterations
            and (run.final_text or run.tool_calls or ledger.validation_error or ledger.tool_error)
        ):
            for recovery_attempt in range(2):
                if (
                    ledger.result is not None
                    or tracker.consecutive_no_progress >= tracker.max_no_progress
                    or budget.iterations >= budget.max_iterations
                ):
                    break
                # A recovery turn must observe only errors produced by that turn;
                # otherwise the first failed tool call closes the recovery stream
                # before the Agent can submit the already collected candidate.
                ledger.validation_error = None
                ledger.tool_error = None
                ledger.budget_exhausted = None
                recovery = types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            text=(
                                f"이전 응답은 허용된 종료 형식이 아니었습니다. 제한된 recovery {recovery_attempt + 1}/2입니다. 새 분석을 시작하지 마세요. "
                                "방금 발생한 Tool 오류를 재시도하지 말고 이미 수집한 관찰만 사용하여 전체 candidate를 validate_analysis Tool에 전달하세요. "
                                "validate_analysis의 top-level status는 complete, partial, failed 중 하나만 사용하고 confirmed/inferred/unresolved/conflicting은 Evidence/Finding에만 사용하세요. "
                                "validation 응답에 evidence_corrections가 있으면 해당 path, line, excerpt를 그대로 Evidence에 복사해 다시 제출하세요. "
                                "status가 partial이면 errors에 비어 있지 않은 실제 Repository 미확인 사유를 포함하고, "
                                "근거가 충분하면 complete를 선택하세요. "
                                "Evidence status에 absence 같은 값은 사용할 수 없습니다. 부재 주장은 status=unresolved와 absence_scope, absence_pattern, result를 사용하고, positive Evidence는 confirmed/inferred/conflicting 중 하나와 path, line_start, line_end를 사용하세요. line evidence는 search_text hit의 확인된 line을 기준으로 최대 4줄만 사용하세요. "
                                "유효한 candidate를 Tool로 검증하기 전에는 prose로 종료하지 마세요."
                            )
                        )
                    ],
                )
                await consume(runner.run_async(user_id="local-user", session_id=session.id, new_message=recovery))

    try:
        asyncio.run(execute())
    except (BudgetExceededError, PydanticDependencyError) as error:
        run.errors.append(str(error))
    except Exception as error:
        message = redact_sensitive_text(str(error))
        if settings.llm_api_key:
            message = message.replace(settings.llm_api_key, "<REDACTED>")
        run.errors.append(f"ADK 실행 오류: {type(error).__name__}: {message[:500]}")

    if ledger.result is not None:
        data = ledger.result.model_dump(mode="json")
        data["iterations"] = budget.iterations
        try:
            run.result = AnalysisResult.model_validate(data)
        except Exception as error:
            run.errors.append(f"AnalysisResult schema validation failure: {error}")
    elif run.final_text:
        candidate = parse_structured_final(run.final_text)
        if candidate is not None:
            try:
                toolset = AdkRepositoryToolset(repository, ledger, tracker)
                validation = toolset.validate_analysis(
                    status=str(candidate.get("status", "")),
                    summary=str(candidate.get("summary", "")),
                    evidence=candidate.get("evidence", []) if isinstance(candidate.get("evidence", []), list) else [],
                    findings=candidate.get("findings", []) if isinstance(candidate.get("findings", []), list) else [],
                    iterations=int(candidate.get("iterations", budget.iterations)),
                    errors=candidate.get("errors", []) if isinstance(candidate.get("errors", []), list) else [],
                    termination=str(candidate.get("termination", "normal")),
                )
                if validation.get("ok") is not True:
                    error = validation.get("error")
                    if isinstance(error, dict) and error.get("message"):
                        run.errors.append(str(error["message"]))
                elif ledger.result is not None:
                    run.result = ledger.result
            except Exception as error:
                run.errors.append(f"최종 structured result validation failure: {redact_sensitive_text(str(error))}")
        else:
            run.errors.append("Agent 최종 응답을 structured result로 파싱하지 못했습니다.")
    if ledger.validation_error:
        run.errors.append(f"validate_analysis 실패: {ledger.validation_error}")
    if ledger.budget_exhausted:
        run.errors.append(ledger.budget_exhausted)
    if ledger.tool_error:
        run.errors.append(f"Repository Tool 오류: {ledger.tool_error}")
    if tracker.consecutive_no_progress >= tracker.max_no_progress and not any("no-progress" in error for error in run.errors):
        run.errors.append("동일 Tool 반복으로 no-progress 한도에 도달했습니다.")
    if run.result is None:
        try:
            evidence = []
            run.result = AnalysisResult.model_validate(
                {
                    "status": "failed",
                    "summary": "Agent가 검증 가능한 분석 결과를 제출하지 못했습니다.",
                    "evidence": evidence,
                    "findings": [],
                    "iterations": budget.iterations,
                    "errors": run.errors or ["Agent 실행이 완료되지 않았습니다."],
                    "termination": "fallback",
                }
            )
        except Exception as error:
            raise AdkExecutionError(str(error)) from error
    return run
