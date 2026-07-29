#!/usr/bin/env python3
"""Run OpenCode acceptance cases and normalize JSON events for evaluation."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

try:
    from scripts.render_summary import render_summary
except ModuleNotFoundError:  # Direct invocation: python3 scripts/run_opencode_acceptance.py ...
    from render_summary import render_summary

ROOT = Path(__file__).resolve().parents[1]
SKILL_ID = "analyze-repo-for-kubernetes"
AGENT_ID = "kubernetes-migration-analyzer"
DEFAULT_OPENCODE = "opencode"
SENSITIVE = re.compile(r"(?i)(api[_-]?key|token|password|secret)([=:：]\s*)[^\s,}]+")

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def redact(value: Any) -> Any:
    if isinstance(value, str):
        return SENSITIVE.sub(r"\1\2[REDACTED]", value)
    if isinstance(value, dict):
        return {str(key): redact(child) for key, child in value.items()}
    if isinstance(value, list):
        return [redact(child) for child in value]
    return value


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip().strip('"')
    return values


def event_lines(stdout: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(redact(value))
    return events


def output_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def strings_in(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result: list[str] = []
        for child in value.values():
            result.extend(strings_in(child))
        return result
    if isinstance(value, list):
        result = []
        for child in value:
            result.extend(strings_in(child))
        return result
    return []


def event_text(event: dict[str, Any]) -> str:
    return " ".join(strings_in(event))


def event_content(event: dict[str, Any]) -> str:
    part = event.get("part")
    if isinstance(part, dict) and isinstance(part.get("text"), str):
        return part["text"]
    if isinstance(event.get("text"), str):
        return event["text"]
    return event_text(event)


def collect_tool_calls(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    known = {"read", "glob", "grep", "list", "bash", "skill", "edit", "write", "patch", "task"}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            tool = value.get("tool") or value.get("name")
            if isinstance(tool, str) and tool in known:
                calls.append({"tool": tool, "input": redact(value.get("input", value.get("args", {})))})
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for event in events:
        visit(event)
    unique: list[dict[str, Any]] = []
    for call in calls:
        if call not in unique:
            unique.append(call)
    return unique


def normalize_trace(
    events: list[dict[str, Any]],
    stdout: str,
    stderr: str,
    returncode: int,
    command: list[str],
    metadata: dict[str, str],
    status: str,
    reason: str | None = None,
) -> dict[str, Any]:
    calls = collect_tool_calls(events)
    serialized = "\n".join(event_text(event) for event in events)
    all_text = f"{serialized}\n{stdout}\n{stderr}"
    reads: list[str] = []
    for path in re.findall(r"(?:SKILL\.md|references/[A-Za-z0-9._/-]+\.md|assets/[A-Za-z0-9._/-]+\.md)", all_text):
        if path not in reads:
            reads.append(path)
    skill_loaded = SKILL_ID in all_text and ("skill" in all_text.lower() or "SKILL.md" in all_text)
    denials: list[dict[str, str]] = []
    for event in events:
        text = event_text(event)
        lowered = text.lower()
        if "permission" in lowered and any(word in lowered for word in ("deny", "denied", "reject", "rejected")):
            denials.append({"event": text[:500]})
    final_output = ""
    for event in events:
        if event.get("type") in {"text", "message", "assistant"}:
            final_output += "\n" + event_content(event)
    if not final_output:
        final_output = stdout.strip()
    return {
        "status": status,
        "reason": reason,
        "returncode": returncode,
        "command": command,
        "skill": {"id": SKILL_ID, "description": metadata.get("description", ""), "loaded": skill_loaded},
        "agent": AGENT_ID,
        "events": events,
        "tool_calls": calls,
        "supporting_reads": reads,
        "permission_denials": denials,
        "final_output": redact(final_output[-12000:]),
    }


def extract_report(trace: dict[str, Any]) -> dict[str, Any] | None:
    text = str(trace.get("final_output", ""))
    candidates = [text]
    candidates.extend(re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL))
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("schema_version") == "1.0":
            return payload
    return None


def unavailable_trace(case: dict[str, Any], reason: str, metadata: dict[str, str]) -> dict[str, Any]:
    return normalize_trace(
        [],
        "",
        "",
        127,
        [],
        metadata,
        "UNAVAILABLE",
        reason,
    ) | {"case_id": case["id"], "query": case["query"]}


def run_case(
    case: dict[str, Any],
    config: Path,
    opencode: str,
    root: Path,
    home: Path,
    config_dir: Path,
    repository_root: Path | None = None,
    model: str | None = None,
    timeout: float = 180,
    runner: CommandRunner = subprocess.run,
) -> dict[str, Any]:
    metadata = parse_frontmatter(root / "SKILL.md")
    executable = shutil.which(opencode, path=os.environ.get("PATH")) if Path(opencode).name == opencode else opencode
    if not executable or not Path(executable).exists():
        return unavailable_trace(case, "OpenCode executable not found", metadata)

    target = repository_root or (root / case["repository_fixture"]).resolve()
    command = [
        executable,
        "run",
        "--pure",
        "--format",
        "json",
        "--agent",
        AGENT_ID,
        "--dir",
        str(target.resolve()),
    ]
    if model:
        command.extend(["--model", model])
    query = case["query"]
    if case.get("acceptance_type") == "analysis":
        query += (
            "\n\nAcceptance harness instruction: return exactly one JSON object "
            "conforming to schemas/analysis-result.schema.json, without Markdown fences "
            "or additional commentary."
        )
    command.append(query)
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(home),
            "OPENCODE_CONFIG": str(config.resolve()),
            "OPENCODE_CONFIG_DIR": str(config_dir.resolve()),
            "OPENCODE_DISABLE_AUTOUPDATE": "1",
        }
    )
    try:
        result = runner(
            command,
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        partial_stdout = output_text(error.stdout)
        partial_stderr = output_text(error.stderr)
        trace = normalize_trace(
            event_lines(partial_stdout),
            partial_stdout,
            partial_stderr,
            124,
            command,
            metadata,
            "UNAVAILABLE",
            f"OpenCode could not complete: {error}",
        )
        trace.update({"case_id": case["id"], "query": case["query"]})
        return trace
    except OSError as error:
        return unavailable_trace(case, f"OpenCode could not complete: {error}", metadata)

    events = event_lines(result.stdout)
    trace = normalize_trace(
        events,
        result.stdout,
        result.stderr,
        result.returncode,
        command,
        metadata,
        "PASS" if result.returncode == 0 else "FAIL",
        None if result.returncode == 0 else "OpenCode returned a nonzero exit code",
    )
    trace.update({"case_id": case["id"], "query": case["query"]})
    report = extract_report(trace)
    if report is not None:
        trace["report_file"] = "report.json"
        trace["report"] = report
    return trace


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenCode Skill acceptance adapter")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--opencode", default=DEFAULT_OPENCODE)
    parser.add_argument("--model", help="선택적 provider/model 지정")
    parser.add_argument("--timeout", type=float, default=180, help="case별 OpenCode timeout 초")
    parser.add_argument(
        "--repository-root",
        type=Path,
        help="모든 acceptance case를 이 read-only Repository 경로에서 실행합니다.",
    )
    parser.add_argument(
        "--use-existing-home",
        action="store_true",
        help="provider 인증을 위해 현재 HOME을 유지합니다. --pure는 계속 적용됩니다.",
    )
    args = parser.parse_args()
    payload = load_json(args.cases)
    cases = payload.get("cases", []) if isinstance(payload, dict) else []
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="opencode-acceptance-") as temporary:
        temporary_root = Path(temporary)
        home = Path(os.environ.get("HOME", str(temporary_root / "home"))).resolve() if args.use_existing_home else temporary_root / "home"
        config_dir = temporary_root / "config"
        # OPENCODE_CONFIG_DIR is isolated per run, so keep the installed Skill
        # beside the copied agent. This is the discovery root used by the
        # OpenCode CLI in pure acceptance runs.
        installed_skill = config_dir / "skills" / SKILL_ID
        agent_dir = config_dir / "agents"
        home.mkdir(parents=True, exist_ok=True)
        agent_dir.mkdir(parents=True)
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/build_dist.py"), "--output", str(installed_skill)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        shutil.copy2(ROOT / "runtime/agents/kubernetes-migration-analyzer.md", agent_dir / f"{AGENT_ID}.md")
        unavailable_reason: str | None = None
        for case in cases:
            case_dir = args.output_dir / case["id"]
            case_dir.mkdir(parents=True, exist_ok=True)
            if unavailable_reason is not None:
                trace = unavailable_trace(case, unavailable_reason, parse_frontmatter(ROOT / "SKILL.md"))
            else:
                trace = run_case(
                    case,
                    args.config,
                    args.opencode,
                    ROOT,
                    home,
                    config_dir,
                    repository_root=args.repository_root,
                    model=args.model,
                    timeout=args.timeout,
                )
                if trace["status"] in {"UNAVAILABLE", "SKIP"}:
                    unavailable_reason = trace.get("reason") or "OpenCode acceptance is unavailable"
            report = trace.get("report")
            if isinstance(report, dict):
                safe_report = redact(report)
                (case_dir / "report.json").write_text(
                    json.dumps(safe_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                if report.get("mode") == "summary":
                    try:
                        (case_dir / "report.md").write_text(render_summary(safe_report), encoding="utf-8")
                        trace["rendered_report_file"] = "report.md"
                    except ValueError as error:
                        trace["renderer_error"] = str(error)
                        trace["status"] = "FAIL"
                        trace["reason"] = "Summary renderer rejected the JSON payload"
            (case_dir / "trace.json").write_text(
                json.dumps(redact(trace), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            print(f"{case['id']}: {trace['status']}" + (f" ({trace['reason']})" if trace.get("reason") else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
