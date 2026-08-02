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
        }
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
