#!/usr/bin/env python3
"""Measure context and execution metadata from normalized OpenCode traces.

The report records only values present in traces or files that were actually
loaded. It leaves provider usage as null when the OpenCode event stream does
not expose usage data.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def trace_paths(root: Path) -> list[Path]:
    if root.is_file() and root.name == "trace.json":
        return [root]
    return sorted(path for path in root.rglob("trace.json") if path.is_file())


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def usage_values(events: list[Any]) -> dict[str, int] | None:
    """Collect explicitly reported usage fields without estimating tokens."""
    found: list[dict[str, int]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            usage = value.get("usage")
            if isinstance(usage, dict):
                numeric = {
                    str(key): child
                    for key, child in usage.items()
                    if isinstance(child, int) and not isinstance(child, bool)
                }
                if numeric and numeric not in found:
                    found.append(numeric)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(events)
    if not found:
        return None
    combined: dict[str, int] = {}
    for usage in found:
        for key, value in usage.items():
            combined[key] = combined.get(key, 0) + value
    return combined


def candidate_roots(trace: dict[str, Any]) -> list[Path]:
    profile = trace.get("profile", {})
    roots: list[Path] = []
    for key in ("skill_discovery_paths", "agent_paths"):
        for value in profile.get(key, []) if isinstance(profile.get(key), list) else []:
            path = Path(value)
            roots.append(path.parent if path.name.endswith((".md",)) else path)
    audit = trace.get("config_audit", {})
    expected = audit.get("expected_skill_path") if isinstance(audit, dict) else None
    if isinstance(expected, str):
        roots.append(Path(expected))
    repository = profile.get("repository_root")
    if isinstance(repository, str):
        roots.append(Path(repository))
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique


def loaded_files(trace: dict[str, Any]) -> dict[str, Any]:
    paths: list[str] = []
    bytes_total = 0
    lines_total = 0
    resolved_files: list[str] = []
    roots = candidate_roots(trace)
    for value in trace.get("supporting_reads", []):
        if not isinstance(value, str):
            continue
        candidates = [Path(value)] if Path(value).is_absolute() else [root / value for root in roots]
        selected: Path | None = None
        for candidate in candidates:
            if candidate.is_file() and any(path_is_within(candidate, root) for root in roots):
                selected = candidate.resolve()
                break
        if selected is None or str(selected) in resolved_files:
            continue
        try:
            content = selected.read_bytes()
        except OSError:
            continue
        resolved_files.append(str(selected))
        paths.append(value)
        bytes_total += len(content)
        lines_total += content.count(b"\n") + (1 if content and not content.endswith(b"\n") else 0)
    return {
        "file_count": len(resolved_files),
        "bytes": bytes_total,
        "lines": lines_total,
        "paths": paths,
        "resolved_paths": resolved_files,
    }


def trace_measurement(path: Path, trace: dict[str, Any]) -> dict[str, Any]:
    profile = trace.get("profile", {}) if isinstance(trace.get("profile"), dict) else {}
    events = trace.get("events", []) if isinstance(trace.get("events"), list) else []
    calls = trace.get("tool_calls", []) if isinstance(trace.get("tool_calls"), list) else []
    usage = usage_values(events)
    step_events = [
        event for event in events
        if isinstance(event, dict)
        and str(event.get("type", "")).lower() in {"step_start", "step_finish", "step"}
    ]
    return {
        "trace": str(path),
        "case_id": trace.get("case_id"),
        "repeat": path.parent.parent.name if path.parent.parent.name.startswith("repeat-") else None,
        "status": trace.get("status"),
        "mode": profile.get("mode"),
        "cwd": profile.get("cwd"),
        "home": profile.get("environment", {}).get("HOME", profile.get("home"))
        if isinstance(profile, dict)
        else None,
        "opencode_config": profile.get("environment", {}).get("OPENCODE_CONFIG", profile.get("opencode_config"))
        if isinstance(profile, dict)
        else None,
        "opencode_config_dir": profile.get("environment", {}).get("OPENCODE_CONFIG_DIR", profile.get("opencode_config_dir"))
        if isinstance(profile, dict)
        else None,
        "skill_discovery_paths": profile.get("skill_discovery_paths", []),
        "agent_paths": profile.get("agent_paths", []),
        "command_path": profile.get("command_path"),
        "provider": profile.get("provider"),
        "model": profile.get("model"),
        "elapsed_seconds": trace.get("elapsed_seconds"),
        "tool_call_count": len(calls),
        "event_count": len(events),
        "step_event_count": len(step_events) if step_events else None,
        "provider_usage": usage,
        "loaded_files": loaded_files(trace),
        "repository_unchanged": trace.get("repository", {}).get("unchanged")
        if isinstance(trace.get("repository"), dict)
        else None,
        "log_files": [trace.get(key) for key in ("stdout_file", "stderr_file") if trace.get(key)],
    }


def summarize(measurements: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for measurement in measurements:
        grouped[str(measurement.get("mode"))].append(measurement)
    profiles: dict[str, Any] = {}
    for mode, entries in sorted(grouped.items()):
        profiles[mode] = {
            "run_count": len(entries),
            "statuses": sorted({entry.get("status") for entry in entries}),
            "total_loaded_bytes": sum(entry["loaded_files"]["bytes"] for entry in entries),
            "total_loaded_lines": sum(entry["loaded_files"]["lines"] for entry in entries),
            "total_tool_calls": sum(entry["tool_call_count"] for entry in entries),
            "elapsed_seconds": sum(
                entry["elapsed_seconds"]
                for entry in entries
                if isinstance(entry.get("elapsed_seconds"), (int, float))
            ),
            "provider_usage_available": all(
                entry.get("provider_usage") is not None for entry in entries
            ),
        }
    return profiles


def measure(traces: Path) -> dict[str, Any]:
    measurements: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in trace_paths(traces):
        try:
            payload = load_json(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            errors.append(f"{path}: {error}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"{path}: trace is not an object")
            continue
        measurements.append(trace_measurement(path, payload))
    return {
        "schema_version": "1.0",
        "trace_root": str(traces.resolve()),
        "trace_count": len(measurements),
        "measurements": measurements,
        "profiles": summarize(measurements),
        "errors": errors,
        "usage_policy": "provider_usage is null when the trace does not expose explicit usage fields; no token estimate is made",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure loaded OpenCode context from normalized traces.")
    parser.add_argument("--traces", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = measure(args.traces)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"trace_count": result["trace_count"], "errors": result["errors"]}, ensure_ascii=False))
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
