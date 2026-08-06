"""Development-only live acceptance gate for the Phase 1 ADK path."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from devtools.env_file import EnvFileLoadResult, load_environment
from migration_assistant.analysis import analyze
from migration_assistant.config import Settings
from migration_assistant.exploration_policy import DEFAULT_MIGRATION_POLICY
from migration_assistant.repository_tools import redact_sensitive_text, redact_sensitive_value
from migration_assistant.target import SafetyBudget


GATE_REQUIRED_RUNS = 3


@dataclass(frozen=True)
class AcceptanceRun:
    output_path: Path
    exit_code: int
    status: str
    terminal: bool
    tool_calls: tuple[str, ...]
    evidence_count: int
    positive_evidence_count: int
    protocol_error_codes: tuple[str, ...]
    protocol_error_fields: tuple[str | None, ...] = ()
    protocol_error_inputs: tuple[str | None, ...] = ()
    evidence_provenance: tuple[dict[str, object], ...] = ()
    provenance_summary: Mapping[str, object] = field(default_factory=dict)
    recovery_attempts: int = 0
    validation_attempts: int = 0
    prebinding_rejections: int = 0
    inline_corrections: int = 0
    max_no_progress_seen: int = 0
    recovery_cap: int = 1
    validation_cap: int = 2
    prebinding_cap: int = 1
    inline_correction_cap: int = 3
    no_progress_cap: int = 3
    telemetry_valid: bool = True
    telemetry_error: str | None = None
    error_type: str | None = None
    error_message: str | None = None

    @property
    def unobserved_evidence_count(self) -> int:
        """Positive Evidence cited without any observation of its lines."""

        return sum(1 for item in self.evidence_provenance if not item.get("sources"))

    def as_summary(self) -> dict[str, object]:
        summary: dict[str, object] = {
            "output_path": str(self.output_path),
            "exit": self.exit_code,
            "status": self.status,
            "terminal": self.terminal,
            "tool_calls": list(self.tool_calls),
            "evidence_count": self.evidence_count,
            "positive_evidence_count": self.positive_evidence_count,
            "protocol_error_codes": list(self.protocol_error_codes),
            "protocol_error_fields": list(self.protocol_error_fields),
            "protocol_error_inputs": list(self.protocol_error_inputs),
            "evidence_provenance": [dict(item) for item in self.evidence_provenance],
            "provenance_summary": dict(self.provenance_summary),
            "unobserved_evidence_count": self.unobserved_evidence_count,
            "recovery_attempts": self.recovery_attempts,
            "validation_attempts": self.validation_attempts,
            "prebinding_rejections": self.prebinding_rejections,
            "inline_corrections": self.inline_corrections,
            "max_no_progress_seen": self.max_no_progress_seen,
            "recovery_cap": self.recovery_cap,
            "validation_cap": self.validation_cap,
            "prebinding_cap": self.prebinding_cap,
            "inline_correction_cap": self.inline_correction_cap,
            "no_progress_cap": self.no_progress_cap,
            "telemetry_valid": self.telemetry_valid,
        }
        if self.telemetry_error is not None:
            summary["telemetry_error"] = self.telemetry_error
        if self.error_type is not None:
            summary["error_type"] = self.error_type
        if self.error_message is not None:
            summary["error_message"] = self.error_message
        return summary


def _is_success(run: AcceptanceRun) -> bool:
    return (
        run.exit_code == 0
        and run.status == "complete"
        and run.terminal
        and "validate_analysis" in run.tool_calls
        and run.positive_evidence_count > 0
        and run.telemetry_valid
        and run.unobserved_evidence_count == 0
        and run.recovery_attempts <= run.recovery_cap
        and run.validation_attempts <= run.validation_cap
        and run.prebinding_rejections <= run.prebinding_cap
        and run.inline_corrections <= run.inline_correction_cap
        and run.max_no_progress_seen <= run.no_progress_cap
    )


def evaluate_runs(
    runs: Sequence[AcceptanceRun], required: int = GATE_REQUIRED_RUNS
) -> dict[str, object]:
    """Purely aggregate deterministic gate criteria without invoking a model."""

    successes = sum(_is_success(run) for run in runs)
    return {
        "passed": len(runs) == required and successes == required,
        "successes": successes,
        "required": required,
        "gate_mode": len(runs) == required,
        "runs": [run.as_summary() for run in runs],
    }


_OBSERVATION_TOOLS = frozenset({"search_text", "read_file", "read_file_lines"})
_ALLOWED_CONTEXT_PROJECTION_FIELDS = frozenset({"question_id", "importance", "signal_rule_ids"})


def evaluate_trajectory(trajectory: Mapping[str, Any]) -> dict[str, object]:
    """Report metrics from one recorded exploration trajectory.

    This never enforces a fixed pass/fail threshold (e.g. a minimum
    question-coverage count or `duplicate_call_count == 0`) -- those would
    overfit to one target repository or one model, which the plan
    explicitly warns against. It only reports; a human or a future Task 7
    gate interprets the numbers.
    """

    tool_calls = [str(name) for name in trajectory.get("tool_calls", []) if isinstance(name, str)]
    first_tool_is_inspect_target = bool(tool_calls) and tool_calls[0] == "inspect_target"

    required_ids = tuple(
        question.question_id for question in DEFAULT_MIGRATION_POLICY.questions
        if question.importance.value == "required"
    )
    dispositions = trajectory.get("required_question_dispositions", {})
    dispositions = dispositions if isinstance(dispositions, Mapping) else {}
    disposed = sum(1 for question_id in required_ids if question_id in dispositions)
    required_question_disposition_rate = disposed / len(required_ids) if required_ids else 1.0

    evidence_items = trajectory.get("evidence", [])
    evidence_items = evidence_items if isinstance(evidence_items, list) else []
    positive_items = [item for item in evidence_items if isinstance(item, Mapping) and item.get("status") != "unresolved"]
    # Two distinct failure modes over the same positive Evidence set:
    # ungrounded = the candidate's own evidence_ids link is missing (a
    # schema-level defect an ADK Pydantic validator would already reject);
    # unobserved = evidence_ids may be present, but no Tool ever actually
    # produced that observation (a provenance-level defect -- see
    # AcceptanceRun.unobserved_evidence_count, which this mirrors).
    # `evidence_linked` defaults to True: a live run's AnalysisResult has
    # already passed schema validation by the time it reaches a trajectory.
    ungrounded_positive_value_count = sum(1 for item in positive_items if item.get("evidence_linked", True) is False)
    unobserved_evidence_count = sum(1 for item in positive_items if not item.get("observed", False))

    grounding_events = trajectory.get("grounding_error_events", [])
    grounding_events = grounding_events if isinstance(grounding_events, list) else []
    tool_call_signatures = trajectory.get("tool_call_signatures")
    tool_call_signatures = tool_call_signatures if isinstance(tool_call_signatures, list) else None
    fresh_observation_after_grounding_error = True
    for event in grounding_events:
        if not isinstance(event, Mapping):
            fresh_observation_after_grounding_error = False
            continue
        recovery_index = event.get("recovery_tool_call_index")
        if not isinstance(recovery_index, int) or not (0 <= recovery_index < len(tool_calls)):
            fresh_observation_after_grounding_error = False
            continue
        if tool_calls[recovery_index] not in _OBSERVATION_TOOLS:
            fresh_observation_after_grounding_error = False
            continue
        # When call signatures are available, require the recovery
        # observation to differ from every earlier observation -- a
        # same-tool, same-args resubmit is a repeat, not fresh evidence.
        if tool_call_signatures is not None and recovery_index < len(tool_call_signatures):
            recovery_signature = tool_call_signatures[recovery_index]
            prior_observation_signatures = {
                tool_call_signatures[index]
                for index in range(recovery_index)
                if index < len(tool_calls) and tool_calls[index] in _OBSERVATION_TOOLS and index < len(tool_call_signatures)
            }
            if recovery_signature in prior_observation_signatures:
                fresh_observation_after_grounding_error = False

    duplicate_call_count = int(trajectory.get("duplicate_call_count", 0) or 0)
    no_progress_max = int(trajectory.get("no_progress_max", 0) or 0)
    no_progress_cap = int(trajectory.get("no_progress_cap", 0) or 0)
    iteration_count = int(trajectory.get("iteration_count", 0) or 0)
    iteration_budget = int(trajectory.get("iteration_budget", 0) or 0)
    bounded_stop_compliant = no_progress_max <= no_progress_cap and (
        iteration_budget == 0 or iteration_count <= iteration_budget
    )

    context_samples = trajectory.get("context_projection_samples", [])
    context_samples = context_samples if isinstance(context_samples, list) else []
    context_projection_leak_free = all(
        isinstance(sample, Mapping) and set(sample) <= _ALLOWED_CONTEXT_PROJECTION_FIELDS
        for sample in context_samples
    )

    return {
        "first_tool_is_inspect_target": first_tool_is_inspect_target,
        "required_question_disposition_rate": required_question_disposition_rate,
        "ungrounded_positive_value_count": ungrounded_positive_value_count,
        "unobserved_evidence_count": unobserved_evidence_count,
        "fresh_observation_after_grounding_error": fresh_observation_after_grounding_error,
        "duplicate_call_count": duplicate_call_count,
        "no_progress_max": no_progress_max,
        "no_progress_cap": no_progress_cap,
        "bounded_stop_compliant": bounded_stop_compliant,
        "context_projection_leak_free": context_projection_leak_free,
    }


def _outside_target(repository: Path, output: Path) -> Path:
    target = repository.expanduser().resolve(strict=True)
    candidate = output.expanduser().absolute().resolve(strict=False)
    if candidate == target or target in candidate.parents or candidate in target.parents:
        raise ValueError("output directory는 target Repository와 분리되어야 합니다.")
    return candidate


def _commit(repository: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _model_summary(*, env_file: EnvFileLoadResult | None = None) -> dict[str, object]:
    environment_names = (
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "LLM_TIMEOUT_SECONDS",
        "LLM_MAX_TOKENS",
    )
    present = {name: name in os.environ for name in environment_names}
    injected_keys = frozenset() if env_file is None else env_file.injected_keys
    sources = {
        name: (
            "env_file"
            if name in injected_keys
            else "environment"
            if present[name]
            else "package_default"
        )
        for name in environment_names
    }
    environment_summary: dict[str, object] = {
        name: {"present": present[name], "source": sources[name]}
        for name in environment_names
    }
    env_file_path = (
        str(env_file.selected_path)
        if env_file is not None and env_file.selected_path is not None
        else None
    )
    try:
        settings = Settings.from_environment()
        summary: dict[str, object] = {
            "llm_base_url": settings.llm_base_url,
            "llm_base_url_source": sources["LLM_BASE_URL"],
            "llm_model": settings.llm_model,
            "llm_model_source": sources["LLM_MODEL"],
            "llm_timeout_seconds": settings.llm_timeout_seconds,
            "llm_timeout_seconds_source": sources["LLM_TIMEOUT_SECONDS"],
            "llm_max_tokens": settings.llm_max_tokens,
            "llm_max_tokens_source": sources["LLM_MAX_TOKENS"],
            "llm_api_key_configured": bool(settings.llm_api_key),
            "environment_variables": environment_summary,
        }
    except ValueError:
        summary = {
            "configuration": "invalid",
            "environment_variables": environment_summary,
        }
    if env_file is not None:
        summary["env_file_path"] = env_file_path
    return redact_sensitive_value(summary)  # type: ignore[return-value]


def _budget_summary(budget: SafetyBudget) -> dict[str, object]:
    return {
        "max_file_size_bytes": budget.max_file_size_bytes,
        "max_files": budget.max_files,
        "max_explorations": budget.max_explorations,
        "max_iterations": budget.max_iterations,
        "max_total_bytes": budget.max_total_bytes,
        "max_search_results": budget.max_search_results,
        "max_no_progress": budget.max_no_progress,
        "max_tool_response_bytes": budget.max_tool_response_bytes,
    }


def _protocol_error_codes(metadata: Mapping[str, object]) -> tuple[str, ...]:
    issues = metadata.get("protocol_issues", [])
    if not isinstance(issues, list):
        return ()
    codes: list[str] = []
    for issue in issues:
        if isinstance(issue, Mapping) and isinstance(issue.get("code"), str):
            codes.append(issue["code"])
    return tuple(codes)


def _protocol_error_fields(metadata: Mapping[str, object]) -> tuple[str | None, ...]:
    """JSONPath of each protocol error, aligned with _protocol_error_codes."""

    issues = metadata.get("protocol_issues", [])
    if not isinstance(issues, list):
        return ()
    fields: list[str | None] = []
    for issue in issues:
        if isinstance(issue, Mapping) and isinstance(issue.get("code"), str):
            path = issue.get("field_path")
            fields.append(path if isinstance(path, str) else None)
    return tuple(fields)


def _protocol_error_inputs(metadata: Mapping[str, object]) -> tuple[str | None, ...]:
    """Shape of each rejected argument, aligned with _protocol_error_codes."""

    issues = metadata.get("protocol_issues", [])
    if not isinstance(issues, list):
        return ()
    inputs: list[str | None] = []
    for issue in issues:
        if isinstance(issue, Mapping) and isinstance(issue.get("code"), str):
            rejected = issue.get("rejected_input")
            inputs.append(rejected if isinstance(rejected, str) else None)
    return tuple(inputs)


def _evidence_provenance(metadata: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    """Per-Evidence observation sources; empty sources mean an unobserved citation."""

    entries = metadata.get("evidence_provenance", [])
    if not isinstance(entries, list):
        return ()
    attribution: list[dict[str, object]] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        sources = entry.get("sources")
        attribution.append(
            {
                "id": entry.get("id") if isinstance(entry.get("id"), str) else None,
                "sources": [str(item) for item in sources] if isinstance(sources, list) else [],
            }
        )
    return tuple(attribution)


def _provenance_summary(metadata: Mapping[str, object]) -> dict[str, object]:
    summary = metadata.get("provenance_summary", {})
    return dict(summary) if isinstance(summary, Mapping) else {}


def _error_summary(error: BaseException) -> dict[str, object]:
    message = redact_sensitive_text(str(error))
    try:
        api_key = Settings.from_environment().llm_api_key
    except ValueError:
        api_key = None
    if api_key:
        message = message.replace(api_key, "<REDACTED>")
    return redact_sensitive_value({
        "error_type": type(error).__name__,
        "error_message": message[:500],
    })  # type: ignore[return-value]


def _run_control_telemetry(metadata: Mapping[str, object]) -> dict[str, object]:
    """Read run-control counts fail-closed without inferring missing zeros."""

    value = metadata.get("run_control")
    if not isinstance(value, Mapping):
        return {"telemetry_valid": False, "telemetry_error": "run_control telemetry가 없습니다."}
    fields = (
        "recovery_attempts", "validation_attempts", "prebinding_rejections",
        "inline_corrections", "max_no_progress_seen", "recovery_cap",
        "validation_cap", "prebinding_cap", "inline_correction_cap", "no_progress_cap",
    )
    if any(not isinstance(value.get(name), int) or value.get(name) < 0 for name in fields):
        return {"telemetry_valid": False, "telemetry_error": "run_control telemetry 형식이 올바르지 않습니다."}
    return {name: int(value[name]) for name in fields} | {"telemetry_valid": True}


def _safe_evidence_items(result: object) -> tuple[object, ...]:
    try:
        evidence = getattr(result, "evidence", ())
        if evidence is None or isinstance(evidence, (str, bytes, Mapping)):
            return ()
        return tuple(evidence)
    except Exception:
        return ()


def _positive_line_backed_evidence_count(result: object) -> int:
    count = 0
    for item in _safe_evidence_items(result):
        try:
            status = getattr(item, "status", None)
            path = getattr(item, "path", None)
            line_start = getattr(item, "line_start", None)
            line_end = getattr(item, "line_end", None)
            if (
                status != "unresolved"
                and isinstance(path, str)
                and bool(path.strip())
                and isinstance(line_start, int)
                and isinstance(line_end, int)
                and line_start > 0
                and line_end >= line_start
            ):
                count += 1
        except Exception:
            continue
    return count


def _run_once(
    repository: Path,
    output: Path,
    budget: SafetyBudget,
    analyze_fn: Callable[..., Any],
) -> AcceptanceRun:
    metadata: dict[str, object] = {}
    try:
        result = analyze_fn(
            repository,
            output,
            max_iterations=budget.max_iterations,
            run_metadata=metadata,
        )
        status = str(getattr(result, "status", "failed"))
        exit_code = {"complete": 0, "partial": 2, "failed": 1}.get(status, 1)
        evidence_items = _safe_evidence_items(result)
        evidence_count = len(evidence_items)
        positive_evidence_count = _positive_line_backed_evidence_count(result)
    except Exception as error:
        status = "error"
        exit_code = 1
        evidence_count = 0
        positive_evidence_count = 0
        error_details = _error_summary(error)
    else:
        error_details = {}

    telemetry = _run_control_telemetry(metadata)

    tool_calls = metadata.get("tool_calls", ())
    if not isinstance(tool_calls, (list, tuple)):
        tool_calls = ()
    return AcceptanceRun(
        output_path=output,
        exit_code=exit_code,
        status=status,
        terminal=metadata.get("terminal") is True,
        tool_calls=tuple(str(name) for name in tool_calls),
        evidence_count=evidence_count,
        positive_evidence_count=positive_evidence_count,
        protocol_error_codes=_protocol_error_codes(metadata),
        protocol_error_fields=_protocol_error_fields(metadata),
        protocol_error_inputs=_protocol_error_inputs(metadata),
        evidence_provenance=_evidence_provenance(metadata),
        provenance_summary=_provenance_summary(metadata),
        recovery_attempts=int(telemetry.get("recovery_attempts", 0)),
        validation_attempts=int(telemetry.get("validation_attempts", 0)),
        prebinding_rejections=int(telemetry.get("prebinding_rejections", 0)),
        inline_corrections=int(telemetry.get("inline_corrections", 0)),
        max_no_progress_seen=int(telemetry.get("max_no_progress_seen", 0)),
        recovery_cap=int(telemetry.get("recovery_cap", 0)),
        validation_cap=int(telemetry.get("validation_cap", 0)),
        prebinding_cap=int(telemetry.get("prebinding_cap", 0)),
        inline_correction_cap=int(telemetry.get("inline_correction_cap", 0)),
        no_progress_cap=int(telemetry.get("no_progress_cap", 0)),
        telemetry_valid=bool(telemetry.get("telemetry_valid", False)),
        telemetry_error=(
            str(telemetry["telemetry_error"])
            if isinstance(telemetry.get("telemetry_error"), str)
            else None
        ),
        error_type=error_details.get("error_type"),  # type: ignore[arg-type]
        error_message=error_details.get("error_message"),  # type: ignore[arg-type]
    )


def run_acceptance(
    repository: str | Path,
    output_parent: str | Path,
    *,
    runs: int = 3,
    analyze_fn: Callable[..., Any] = analyze,
    env_file: EnvFileLoadResult | None = None,
) -> dict[str, object]:
    """Execute isolated application-boundary runs and return a JSON-safe summary."""

    if runs < 1:
        raise ValueError("--runs는 1 이상의 정수여야 합니다.")
    repository_path = Path(repository).expanduser().resolve(strict=True)
    budget = SafetyBudget()
    output_parent_path = Path(output_parent).expanduser().absolute()
    run_results = [
        _run_once(
            repository_path,
            _outside_target(repository_path, output_parent_path / f"run-{index}"),
            budget,
            analyze_fn,
        )
        for index in range(1, runs + 1)
    ]
    summary = evaluate_runs(run_results, required=GATE_REQUIRED_RUNS)
    summary_errors: dict[str, object] = {}
    for key, builder in (
        ("commit", lambda: _commit(repository_path)),
        ("model", lambda: _model_summary(env_file=env_file)),
        ("budget", lambda: _budget_summary(budget)),
    ):
        try:
            summary[key] = builder()
        except Exception as error:
            summary_errors[key] = _error_summary(error)
    if summary_errors:
        summary["summary_errors"] = summary_errors
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 1 ADK development-only live acceptance gate")
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output-parent", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=GATE_REQUIRED_RUNS)
    parser.add_argument("--env-file", type=Path, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        env_file = load_environment(args.repository, explicit_path=args.env_file)
        summary = run_acceptance(
            args.repository,
            args.output_parent,
            runs=args.runs,
            env_file=env_file,
        )
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    except Exception as error:
        summary = {
            "passed": False,
            "successes": 0,
            "required": 3,
            "error": type(error).__name__,
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
