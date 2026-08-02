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

from .adk_tools import DuplicateTracker, ValidationLedger
from .agent import AgentApplication
from .provenance import ObservationProvenance, evidence_sources
from .analysis import AnalysisResult, PydanticDependencyError
from .config import Settings
from .repository_tools import RepositoryTools, redact_sensitive_text
from .target import BudgetExceededError, SafetyBudget
from .tool_contract import PUBLIC_AGENT_TOOL_NAMES
from .tool_protocol import RunControlLedger, RunPhase, ToolErrorCode, error_envelope


class AdkExecutionError(RuntimeError):
    """Raised for non-configuration ADK execution failures."""


@dataclass
class AdkRun:
    result: AnalysisResult | None = None
    errors: list[str] = field(default_factory=list)
    final_text: str = ""
    tool_calls: list[str] = field(default_factory=list)
    terminal: bool = False
    protocol_issues: list[dict[str, object]] = field(default_factory=list)
    recovery_attempts: int = 0
    evidence_provenance: list[dict[str, object]] = field(default_factory=list)
    provenance_summary: dict[str, object] = field(default_factory=dict)


_FENCED_JSON = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def _recovery_prompt(control: RunControlLedger, attempt: int, tool_names: tuple[str, ...]) -> str:
    issue = control.protocol_issue
    if issue is None:
        return (
            f"이전 응답은 terminal Tool 결과가 아니었습니다. 제한된 recovery {attempt}/{control.max_recovery_attempts}입니다. "
            "새 분석을 시작하지 말고 이미 수집한 근거로 전체 candidate를 validate_analysis에 제출하세요."
        )
    actions = control.allowed_next_actions(tool_names)
    field = f" 실패 field={issue.field_path}." if issue.field_path else ""
    return (
        f"Tool protocol 오류 code={issue.code.value}, category={issue.category}.{field} "
        f"제한된 recovery {attempt}/{control.max_recovery_attempts}입니다. 허용된 다음 Tool은 {', '.join(actions) or '없음'}입니다. "
        "오류 메시지에 없는 사실을 추정하지 말고, 동일한 실패 호출을 반복하지 마세요. "
        "candidate 오류이면 의미를 자동 생성하지 말고 전체 candidate의 보고된 field만 수정해 validate_analysis에 다시 제출하세요."
    )


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
    provenance = ObservationProvenance()
    agent = AgentApplication(settings).build_root_agent(
        repository_tools=repository,
        ledger=ledger,
        tracker=tracker,
        budget=budget,
        model_override=model_override,
        control=control,
        provenance=provenance,
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
                    if control.protocol_issue is not None:
                        issue_payload = error_envelope(
                            control.protocol_issue,
                            allowed_next_actions=control.allowed_next_actions(PUBLIC_AGENT_TOOL_NAMES),
                        )["error"]
                        # Measurement only; the envelope the model received above
                        # deliberately omits it.
                        if control.protocol_issue.rejected_input is not None:
                            issue_payload["rejected_input"] = control.protocol_issue.rejected_input
                        if not run.protocol_issues or run.protocol_issues[-1] != issue_payload:
                            run.protocol_issues.append(issue_payload)
                        if control.protocol_issue.code not in {
                            ToolErrorCode.CANDIDATE_SCHEMA,
                            ToolErrorCode.EVIDENCE_GROUNDING,
                        }:
                            await events.aclose()
                            break
                    content = getattr(event, "content", None)
                    if content is not None and getattr(content, "role", None) == "model":
                        text = "\n".join(part.text for part in (content.parts or []) if getattr(part, "text", None))
                        if text:
                            run.final_text = redact_sensitive_text(text)
                    if ledger.result is not None:
                        run.terminal = True
                        control.phase = RunPhase.DONE
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
            and (run.final_text or run.tool_calls or ledger.validation_error or ledger.tool_error or control.protocol_issue)
        ):
            for recovery_attempt in range(control.max_recovery_attempts):
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
                control.recovery_attempts += 1
                recovery = types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            text=_recovery_prompt(control, recovery_attempt + 1, PUBLIC_AGENT_TOOL_NAMES)
                        )
                    ],
                )
                await consume(runner.run_async(user_id="local-user", session_id=session.id, new_message=recovery))
                issue = control.protocol_issue
                if issue is not None:
                    fingerprint = f"{issue.field_path or '$'}:{','.join(control.allowed_next_actions(PUBLIC_AGENT_TOOL_NAMES))}"
                    if control.action_repeated(issue.code, fingerprint):
                        run.errors.append("동일 protocol 오류와 recovery action이 반복되어 no-progress로 종료했습니다.")
                        break
        run.recovery_attempts = control.recovery_attempts

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
            run.errors.append(f"AnalysisResult schema 검증에 실패했습니다: {error}")
    elif run.final_text and control.protocol_issue is None:
        candidate = parse_structured_final(run.final_text)
        if candidate is not None:
            try:
                validation = repository.validate_analysis(candidate)
                if validation.get("valid") is not True:
                    run.errors.extend(str(item) for item in validation.get("errors", []))
                else:
                    fallback = dict(candidate)
                    if fallback.get("status") == "complete":
                        fallback["status"] = "partial"
                        existing_errors = fallback.get("errors")
                        fallback["errors"] = [
                            *(existing_errors if isinstance(existing_errors, list) else []),
                            "validate_analysis terminal Tool 호출이 없어 complete로 승인할 수 없습니다.",
                        ]
                    fallback["iterations"] = budget.iterations
                    fallback["termination"] = "posthoc_fallback"
                    run.result = AnalysisResult.model_validate(fallback)
            except Exception as error:
                run.errors.append(f"최종 structured result 검증에 실패했습니다: {redact_sensitive_text(str(error))}")
        else:
            run.errors.append("Agent 최종 응답을 structured result로 파싱하지 못했습니다.")
    if ledger.validation_error:
        run.errors.append(f"validate_analysis 실패: {ledger.validation_error}")
    if ledger.budget_exhausted:
        run.errors.append(ledger.budget_exhausted)
    if ledger.tool_error:
        run.errors.append(f"Repository Tool 오류: {ledger.tool_error}")
    if run.protocol_issues and not run.errors:
        latest = run.protocol_issues[-1]
        run.errors.append(f"Tool protocol 오류: {latest.get('code')}: {latest.get('message')}")
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
    # Measurement only: attribution never gates the result above.
    run.provenance_summary = provenance.summary()
    if run.result is not None:
        run.evidence_provenance = evidence_sources(run.result.evidence, provenance)
    return run
