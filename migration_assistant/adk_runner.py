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
from .repository_tools import RepositoryTools
from .target import BudgetExceededError, SafetyBudget


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
    agent = AgentApplication(settings).build_root_agent(
        repository_tools=repository,
        ledger=ledger,
        tracker=tracker,
        budget=budget,
        model_override=model_override,
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
                            run.final_text = text
                    if ledger.result is not None:
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
            recovery = types.Content(
                role="user",
                parts=[
                    types.Part(
                        text=(
                            "이전 응답은 허용된 종료 형식이 아니었습니다. 새 분석을 시작하지 마세요. "
                            "이미 수집한 관찰만 사용하여 전체 candidate를 validate_analysis Tool에 전달하세요. "
                            "status가 partial이면 errors에 비어 있지 않은 실제 Repository 미확인 사유를 포함하고, "
                            "근거가 충분하면 complete를 선택하세요. "
                            "Evidence status에 absence 같은 값은 사용할 수 없습니다. 부재 주장은 status=unresolved와 absence_scope, absence_pattern, result를 사용하고, positive Evidence는 confirmed/inferred/conflicting 중 하나와 path, line_start, line_end를 사용하세요. "
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
        message = str(error)
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
                result = AnalysisResult.model_validate(candidate)
                if result.status == "complete" and run.tool_calls:
                    run.errors.append("validate_analysis Tool 성공 없이 complete로 종료할 수 없습니다.")
                else:
                    run.result = result
            except Exception as error:
                run.errors.append(f"최종 structured result validation failure: {error}")
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
        fatal = ledger.validation_error is not None or any(
            "ADK 실행 오류" in error or "schema validation failure" in error
            for error in run.errors
        )
        try:
            evidence = []
            seen: set[tuple[object, object, object]] = set()
            for item in ledger.observations:
                key = (item.get("path"), item.get("line_start"), item.get("line_end"))
                if key in seen:
                    continue
                seen.add(key)
                evidence.append(
                    {
                        "status": "confirmed",
                        "path": item.get("path"),
                        "line_start": item.get("line_start"),
                        "line_end": item.get("line_end"),
                        "text": item.get("text"),
                    }
                )
            run.result = AnalysisResult.model_validate(
                {
                    "status": "failed" if fatal or not evidence else "partial",
                    "summary": "Agent가 검증 가능한 분석 결과를 제출하지 못했습니다." if fatal else "Agent 분석이 부분 완료되었습니다.",
                    "evidence": evidence,
                    "iterations": budget.iterations,
                    "errors": run.errors or ["Agent 실행이 완료되지 않았습니다."],
                }
            )
        except Exception as error:
            raise AdkExecutionError(str(error)) from error
    elif ledger.result is None and run.errors and run.result.status == "complete" and any(
        not error.startswith("Repository Tool 오류:") for error in run.errors
    ):
        data = run.result.model_dump(mode="json")
        data["status"] = "partial"
        data["errors"] = [*data.get("errors", []), *run.errors]
        run.result = AnalysisResult.model_validate(data)
    return run
