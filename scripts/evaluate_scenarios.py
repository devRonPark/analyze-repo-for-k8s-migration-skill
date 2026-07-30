#!/usr/bin/env python3
"""Evaluate externally generated analysis reports against executable scenarios."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts/validate_report.py"
REQUIRED_CASE_FIELDS = {
    "id",
    "query",
    "repository_fixture",
    "report_mode",
    "expected_behavior",
    "forbidden_behavior",
    "repository_snapshot",
}
OPENCODE_CASE_FIELDS = {
    "id",
    "query",
    "repository_fixture",
    "acceptance_type",
    "expected_behavior",
    "forbidden_behavior",
    "repository_snapshot",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_path(value: str, root: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def repository_files(root: Path) -> dict[str, Path]:
    return {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def repository_snapshot_errors(root: Path, expected: dict[str, str]) -> list[str]:
    errors: list[str] = []
    actual = repository_files(root)
    if set(actual) != set(expected):
        errors.append("repository changed: file set differs from scenario snapshot")
        return errors
    for relative, expected_content in expected.items():
        try:
            content = actual[relative].read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            errors.append(f"repository changed: cannot read {relative}")
            continue
        if content != expected_content:
            errors.append(f"repository changed: content differs at {relative}")
    return errors


def fixture_snapshot_errors(case: dict[str, Any]) -> list[str]:
    fixture = resolve_path(case.get("repository_fixture", ""), ROOT)
    if not fixture.is_dir():
        return [f"repository fixture is missing: {fixture}"]
    snapshot = case.get("repository_snapshot", {})
    if not isinstance(snapshot, dict):
        return ["repository snapshot is not an object"]
    return repository_snapshot_errors(fixture, snapshot)


def report_validation_errors(
    report_path: Path,
    mode: str,
    report_format: str,
    message: str,
) -> list[str]:
    validation = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            str(report_path),
            "--mode",
            mode,
            "--format",
            report_format,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if validation.returncode == 0:
        return []
    return [f"{message}: {validation.stdout.strip()}"]


def report_core(payload: Any, text: str) -> dict[str, Any]:
    if isinstance(payload, dict):
        candidates = sorted(
            component.get("name")
            for component in payload.get("components", [])
            if isinstance(component, dict) and isinstance(component.get("name"), str)
        )
        dependencies = sorted(
            f"{dependency.get('source')}->{dependency.get('target')}"
            for dependency in payload.get("dependencies", [])
            if isinstance(dependency, dict)
            and isinstance(dependency.get("source"), str)
            and isinstance(dependency.get("target"), str)
        )
        return {
            "candidate_names": candidates,
            "dependency_edges": dependencies,
            "readiness_verdict": payload.get("design_input_verdict"),
        }
    candidates = sorted(re.findall(r"^### 배포 대상: (\S+)", text, re.MULTILINE))
    verdict = re.findall(r"^- 판정: (설계 입력 충분|추가 정보 필요|분석 불가)$", text, re.MULTILINE)
    return {"candidate_names": candidates, "dependency_edges": [], "readiness_verdict": verdict[-1] if verdict else None}


def report_statuses(payload: Any, text: str) -> set[str]:
    statuses: set[str] = set()
    if isinstance(payload, dict):
        def visit(value: Any) -> None:
            if isinstance(value, dict):
                if value.get("status") in {"확인됨", "추정됨", "미확인", "상충됨"}:
                    statuses.add(value["status"])
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        visit(payload)
    else:
        statuses.update(re.findall(r"상태: (확인됨|추정됨|미확인|상충됨)", text))
    return statuses


def trace_events(actual_case_dir: Path, case: dict[str, Any]) -> list[str]:
    trace_name = case.get("trace_file", "trace.json")
    trace_path = actual_case_dir / trace_name
    if not trace_path.is_file():
        return []
    payload = load_json(trace_path)
    events = payload if isinstance(payload, list) else payload.get("events", []) if isinstance(payload, dict) else []
    names: list[str] = []
    for event in events:
        if isinstance(event, dict):
            names.extend(str(event.get(key)) for key in ("name", "event", "tool") if event.get(key) is not None)
    return names


def validate_case(case: dict[str, Any], actual_dir: Path) -> dict[str, Any]:
    case_id = case.get("id", "<unknown>")
    errors: list[str] = []
    case_dir = actual_dir / case_id
    report_path = case_dir / case.get("report_file", "report.json")
    expected_behavior = case.get("expected_behavior", {})
    forbidden_behavior = case.get("forbidden_behavior", {})

    errors.extend(fixture_snapshot_errors(case))

    if not report_path.is_file():
        errors.append(f"missing actual report: {report_path}")
        return {"id": case_id, "passed": False, "errors": errors}

    report_format = case.get("report_format", "json")
    errors.extend(
        report_validation_errors(
            report_path,
            case["report_mode"],
            report_format,
            "report validation failed",
        )
    )

    try:
        payload = load_json(report_path) if report_format == "json" else None
        text = report_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        errors.append(f"actual report cannot be read: {error}")
        return {"id": case_id, "passed": False, "errors": errors}

    core = report_core(payload, text)
    for candidate in expected_behavior.get("candidate_names", []):
        if candidate not in core["candidate_names"]:
            errors.append(f"candidate fact missing: {candidate}")
    for edge in expected_behavior.get("dependency_edges", []):
        if edge not in core["dependency_edges"]:
            errors.append(f"dependency fact missing: {edge}")
    missing_statuses = set(expected_behavior.get("evidence_statuses", [])) - report_statuses(payload, text)
    for status in sorted(missing_statuses):
        errors.append(f"evidence status missing: {status}")
    if "readiness_verdict" in expected_behavior and core["readiness_verdict"] != expected_behavior["readiness_verdict"]:
        errors.append(f"readiness verdict mismatch: {core['readiness_verdict']}")

    serialized = text if report_format == "markdown" else json.dumps(payload, ensure_ascii=False)
    for forbidden in forbidden_behavior.get("text", []):
        if forbidden in serialized:
            errors.append(f"forbidden behavior present: {forbidden}")
    event_names = trace_events(case_dir, case)
    for forbidden_event in forbidden_behavior.get("trace_events", []):
        if forbidden_event in event_names:
            errors.append(f"forbidden trace event present: {forbidden_event}")

    repeat_name = case.get("repeat_report")
    if repeat_name:
        repeat_path = case_dir / repeat_name
        if repeat_path.is_file():
            try:
                repeat_payload = load_json(repeat_path)
                repeat_core = report_core(repeat_payload, repeat_path.read_text(encoding="utf-8"))
                for field in expected_behavior.get("stable_core_fields", []):
                    if core.get(field) != repeat_core.get(field):
                        errors.append(f"repeat core field mismatch: {field}")
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                errors.append(f"repeat report cannot be read: {error}")

    return {
        "id": case_id,
        "passed": not errors,
        "errors": errors,
        "repository_unchanged": not any(error.startswith("repository changed") for error in errors),
        "core": core,
    }


def validate_opencode_case(case: dict[str, Any], actual_dir: Path) -> dict[str, Any]:
    """Evaluate normalized OpenCode traces and direct report output."""
    case_id = case.get("id", "<unknown>")
    errors: list[str] = []
    case_dir = actual_dir / case_id
    trace_path = case_dir / case.get("trace_file", "trace.json")
    errors.extend(fixture_snapshot_errors(case))

    if not trace_path.is_file():
        errors.append(f"missing OpenCode trace: {trace_path}")
        return {"id": case_id, "passed": False, "skipped": False, "errors": errors}
    try:
        trace = load_json(trace_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return {"id": case_id, "passed": False, "skipped": False, "errors": [str(error)]}
    if not isinstance(trace, dict):
        return {"id": case_id, "passed": False, "skipped": False, "errors": ["OpenCode trace is not an object"]}

    status = trace.get("status")
    if status in {"UNAVAILABLE", "SKIP"}:
        return {
            "id": case_id,
            "passed": False,
            "skipped": True,
            "errors": [f"OpenCode acceptance unavailable: {trace.get('reason', status)}"],
        }
    if status != "PASS":
        errors.append(f"OpenCode case status is not PASS: {status}")

    expected = case.get("expected_behavior", {})
    skill = trace.get("skill", {})
    if "skill_loaded" in expected and skill.get("loaded") != expected["skill_loaded"]:
        errors.append(f"Skill loaded mismatch: {skill.get('loaded')}")
    if expected.get("skill_id") and skill.get("id") != expected["skill_id"]:
        errors.append(f"Skill id mismatch: {skill.get('id')}")
    reads = set(trace.get("supporting_reads", []))
    for required in expected.get("required_reads", []):
        if not any(required in path for path in reads):
            errors.append(f"required supporting read missing: {required}")
    for forbidden in case.get("forbidden_behavior", {}).get("reads", []):
        if any(forbidden in path for path in reads):
            errors.append(f"forbidden supporting read present: {forbidden}")

    tools = {call.get("tool") for call in trace.get("tool_calls", []) if isinstance(call, dict)}
    for forbidden in case.get("forbidden_behavior", {}).get("tools", []):
        if forbidden in tools:
            errors.append(f"forbidden tool call present: {forbidden}")
    denials = " ".join(
        str(item.get("event", ""))
        for item in trace.get("permission_denials", [])
        if isinstance(item, dict)
    ).lower()
    for permission in expected.get("permission_denied_for", []):
        if permission.lower() not in denials:
            errors.append(f"permission denial missing for: {permission}")

    final_output = str(trace.get("final_output", ""))
    for required in expected.get("required_output", []):
        if required not in final_output:
            errors.append(f"required response text missing: {required}")
    for forbidden in expected.get("forbidden_output", []):
        if forbidden in final_output:
            errors.append(f"forbidden response text present: {forbidden}")
    for forbidden_tool in expected.get("forbidden_tools", []):
        if forbidden_tool in tools:
            errors.append(f"forbidden tool call present: {forbidden_tool}")

    summary = expected.get("report_mode") == "summary"
    report_name = "report.md" if summary else case.get("report_file", "report.json")
    report_path = case_dir / report_name
    if expected.get("report_mode"):
        if not report_path.is_file():
            errors.append(f"missing normalized OpenCode report: {report_path}")
        else:
            errors.extend(
                report_validation_errors(
                    report_path,
                    expected["report_mode"],
                    "markdown" if summary else "json",
                    "normalized report validation failed",
                )
            )
    if summary and not final_output.startswith("# Kubernetes 설계 입력 요약\n"):
        errors.append("final Summary output does not begin with the report heading")
    return {
        "id": case_id,
        "passed": not errors,
        "skipped": False,
        "errors": errors,
        "repository_unchanged": not any(error.startswith("repository changed") for error in errors),
    }


def evaluate(cases_path: Path, actual_dir: Path) -> dict[str, Any]:
    payload = load_json(cases_path)
    cases = payload.get("cases") if isinstance(payload, dict) else None
    errors: list[str] = []
    if isinstance(payload, dict) and payload.get("suite") == "opencode":
        if not isinstance(cases, list) or len(cases) < 3:
            return {"passed": False, "skipped": False, "cases": [], "errors": ["OpenCode suite must contain at least 3 cases"]}
        results: list[dict[str, Any]] = []
        for case in cases:
            if not isinstance(case, dict) or not OPENCODE_CASE_FIELDS.issubset(case):
                errors.append("OpenCode case is missing a required field")
                continue
            results.append(validate_opencode_case(case, actual_dir))
        hard_failures = any(not result["passed"] and not result.get("skipped") for result in results)
        return {
            "passed": not errors and bool(results) and all(result["passed"] for result in results),
            "skipped": not errors and bool(results) and not hard_failures and all(result.get("skipped") for result in results),
            "cases": results,
            "errors": errors,
        }
    if not isinstance(cases, list) or len(cases) < 8:
        return {"passed": False, "cases": [], "errors": ["scenario suite must contain at least 8 cases"]}
    results: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict) or not REQUIRED_CASE_FIELDS.issubset(case):
            errors.append("scenario case is missing a required field")
            continue
        results.append(validate_case(case, actual_dir))
    return {
        "passed": not errors and all(result["passed"] for result in results),
        "cases": results,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="실제 분석 보고서를 scenario별로 평가합니다.")
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--actual-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = evaluate(args.cases, args.actual_dir)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError) as error:
        result = {"passed": False, "cases": [], "errors": [str(error)]}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["passed"] or result.get("skipped"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
