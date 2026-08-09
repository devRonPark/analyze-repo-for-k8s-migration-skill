#!/usr/bin/env python3
"""Run OpenCode acceptance cases. Summary cases return Agent JSON, which this
harness renders, validates, and finalizes into the retained Markdown output."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

try:
    from scripts.build_dist import SKILL_IDS as BUNDLE_SKILL_IDS, build as build_bundle
    from scripts.install_distribution import install_bundle, render_opencode_mcp_fragment
    from scripts.validate_skill import validate_bundle
    from scripts.project_metadata import ProjectMetadata, load as load_project_metadata
    from scripts.render_summary import render_summary
    from scripts.render_detailed import render_detailed
    from scripts.validate_target_report import finalize as finalize_receipt
except ModuleNotFoundError:  # Direct invocation: python3 scripts/run_opencode_acceptance.py ...
    from build_dist import SKILL_IDS as BUNDLE_SKILL_IDS, build as build_bundle
    from install_distribution import install_bundle, render_opencode_mcp_fragment
    from validate_skill import validate_bundle
    from project_metadata import ProjectMetadata, load as load_project_metadata
    from render_summary import render_summary
    from render_detailed import render_detailed
    from validate_target_report import finalize as finalize_receipt

ROOT = Path(__file__).resolve().parents[1]
PROJECT = load_project_metadata(ROOT)
SKILL_ID = PROJECT.skill_id
AGENT_ID = PROJECT.agent_id
DEFAULT_OPENCODE = "opencode"
SENSITIVE = re.compile(r"(?i)(api[_-]?key|token|password|secret)([=:：]\s*)[^\s,}]+")

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def path_is_within(path: Path, parent: Path) -> bool:
    """Return whether path is parent or one of its descendants."""
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_snapshot(root: Path) -> dict[str, str]:
    """Hash regular files without following links or entering .git."""
    if not root.is_dir():
        return {}
    snapshot: dict[str, str] = {}
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(name for name in dirnames if name != ".git")
        for name in sorted(filenames):
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            try:
                snapshot[relative] = sha256_file(path)
            except OSError:
                snapshot[relative] = "<unreadable>"
    return snapshot


def git_probe(repository_root: Path) -> dict[str, Any]:
    """Collect immutable Git identity evidence outside the OpenCode process."""
    probes: dict[str, Any] = {}
    for name, args in {
        "status": ["git", "-C", str(repository_root), "status", "--short"],
        "revision": ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
        "branch": ["git", "-C", str(repository_root), "symbolic-ref", "--short", "HEAD"],
    }.items():
        try:
            result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=False)
        except OSError as error:
            probes[name] = {"returncode": 127, "stdout": "", "stderr": str(error)}
            continue
        probes[name] = {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    return probes


def repository_integrity(repository_root: Path, before: dict[str, Any]) -> dict[str, Any]:
    after_files = tree_snapshot(repository_root)
    before_files = before.get("files", {})
    changed = sorted(
        set(before_files) ^ set(after_files)
        | {path for path in set(before_files) & set(after_files) if before_files[path] != after_files[path]}
    )
    after_git = git_probe(repository_root)
    return {
        "root": str(repository_root.resolve()),
        "opencode_exists_before": before.get("opencode_exists"),
        "opencode_exists_after": (repository_root / ".opencode").exists(),
        "git_before": before.get("git", {}),
        "git_after": after_git,
        "files_before": len(before_files),
        "files_after": len(after_files),
        "changed_paths": changed,
        "unchanged": not changed and before.get("git", {}) == after_git,
    }


def repository_baseline(repository_root: Path) -> dict[str, Any]:
    return {
        "root": str(repository_root.resolve()),
        "opencode_exists": (repository_root / ".opencode").exists(),
        "git": git_probe(repository_root),
        "files": tree_snapshot(repository_root),
    }


def standard_skill_paths(home: Path, config_dir: Path | None = None) -> list[Path]:
    candidates = [
        home / ".config" / "opencode" / "skills" / SKILL_ID,
        home / ".agents" / "skills" / SKILL_ID,
        home / ".claude" / "skills" / SKILL_ID,
    ]
    if config_dir is not None:
        candidates.insert(0, config_dir / "skills" / SKILL_ID)
    paths: list[Path] = []
    for path in candidates:
        if path not in paths:
            paths.append(path)
    return paths


def standard_agent_paths(home: Path, config_dir: Path | None = None) -> list[Path]:
    candidates = [home / ".config" / "opencode" / "agents" / f"{AGENT_ID}.md"]
    if config_dir is not None:
        candidates.insert(0, config_dir / "agents" / f"{AGENT_ID}.md")
    paths: list[Path] = []
    for path in candidates:
        if path not in paths:
            paths.append(path)
    return paths


def skill_inventory(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir())


def discovery_audit(
    source_root: Path,
    home: Path,
    config_dir: Path | None,
    repository_root: Path,
    mode: str,
) -> dict[str, Any]:
    expected_hash = sha256_file(source_root / "SKILL.md")
    paths = standard_skill_paths(home, config_dir)
    observed: list[dict[str, Any]] = []
    for path in paths:
        item: dict[str, Any] = {"path": str(path), "exists": path.is_dir()}
        skill_file = path / "SKILL.md"
        if skill_file.is_file():
            try:
                item["skill_sha256"] = sha256_file(skill_file)
                item["matches_source"] = item["skill_sha256"] == expected_hash
            except OSError as error:
                item["error"] = str(error)
        observed.append(item)
    roots = {path.parent for path in paths}
    discovered: dict[str, list[str]] = {}
    for root in sorted(roots):
        discovered[str(root)] = skill_inventory(root)
    allowed_paths = {str(path.resolve()) for path in paths if path.exists()}
    stale = [
        item["path"]
        for item in observed
        if item.get("exists") and item.get("matches_source") is False
    ]
    unexpected = sorted(
        skill
        for skills in discovered.values()
        for skill in skills
        if skill != SKILL_ID
    )
    return {
        "mode": mode,
        "repository_root": str(repository_root.resolve()),
        "repository_opencode_path": str((repository_root / ".opencode").resolve()),
        "repository_opencode_exists": (repository_root / ".opencode").exists(),
        "source_skill_path": str((source_root / "SKILL.md").resolve()),
        "expected_skill_sha256": expected_hash,
        "skill_paths": observed,
        "skill_discovery_roots": sorted(str(root.resolve()) for root in roots),
        "discovered_skills": discovered,
        "allowed_existing_skill_paths": sorted(allowed_paths),
        "stale_or_mismatched_skill_paths": stale,
        "unexpected_skill_ids": unexpected,
        "agent_paths": [
            {"path": str(path), "exists": path.is_file()}
            for path in standard_agent_paths(home, config_dir)
        ],
    }


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


def copy_skill(source_root: Path, destination: Path) -> None:
    """Copy only the declared runtime Skill files into an isolated root."""
    entries = [
        line.strip()
        for line in (source_root / "runtime-files.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    destination.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        source = source_root / entry
        target = destination / entry
        if not source.is_file():
            raise FileNotFoundError(f"runtime Skill file is missing: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def copy_bundle(source_root: Path, destination: Path) -> Path:
    """Build and validate a sealed seven-Skill bundle for an isolated run."""
    bundle = build_bundle(source_root, destination)
    errors = validate_bundle(bundle)
    if errors:
        raise ValueError("invalid acceptance bundle: " + "; ".join(errors))
    return bundle


def bundle_skill_paths(config_dir: Path) -> list[Path]:
    return [config_dir / "skills" / skill_id for skill_id in BUNDLE_SKILL_IDS]


def discovery_audit_bundle(
    source_bundle: Path,
    config_dir: Path,
    repository_root: Path,
    mode: str,
) -> dict[str, Any]:
    """Audit only the installed static topology, never target-repository files."""
    source_bundle = source_bundle.resolve()
    config_dir = config_dir.resolve()
    paths = bundle_skill_paths(config_dir)
    expected_hashes = {
        skill_id: sha256_file(source_bundle / "skills" / skill_id / "SKILL.md")
        for skill_id in BUNDLE_SKILL_IDS
    }
    installed = {
        skill_id: sha256_file(config_dir / "skills" / skill_id / "SKILL.md")
        if (config_dir / "skills" / skill_id / "SKILL.md").is_file()
        else None
        for skill_id in BUNDLE_SKILL_IDS
    }
    observed = {path.name for path in (config_dir / "skills").iterdir()} if (config_dir / "skills").is_dir() else set()
    return {
        "mode": mode,
        "repository_root": str(repository_root.resolve()),
        "skill_paths": [str(path.resolve()) for path in paths],
        "expected_skill_ids": list(BUNDLE_SKILL_IDS),
        "observed_skill_ids": sorted(observed),
        "missing_skill_ids": sorted(set(BUNDLE_SKILL_IDS) - observed),
        "unexpected_skill_ids": sorted(observed - set(BUNDLE_SKILL_IDS)),
        "mismatched_skill_ids": sorted(
            skill_id
            for skill_id, actual in installed.items()
            if actual != expected_hashes[skill_id]
        ),
    }


def render_agent(source: Path, destination: Path, skill_path: Path) -> None:
    text = source.read_text(encoding="utf-8")
    temporary_rule = '    "/tmp/opencode-acceptance-*/config/skills/analyze-repo-for-kubernetes/**": allow'
    exact_rule = f'    "{skill_path.resolve().as_posix()}/**": allow'
    text = text.replace(temporary_rule, exact_rule)
    # Isolated HOME must not inherit global external-directory exceptions.
    # The exact temporary Skill path above is the only external Skill path.
    text = "\n".join(
        line
        for line in text.splitlines()
        if '"$HOME/' not in line
    ) + "\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def isolated_config(source: Path, destination: Path, skill_path: Path) -> None:
    config = load_json(source)
    if not isinstance(config, dict):
        raise ValueError("OpenCode config must be a JSON object")
    permissions = config.setdefault("permission", {})
    if not isinstance(permissions, dict):
        raise ValueError("OpenCode permission must be an object")
    permissions["external_directory"] = {f"{skill_path.resolve().as_posix()}/**": "allow"}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def isolated_config_bundle(source: Path, destination: Path, config_dir: Path) -> None:
    """Write an isolated OpenCode config with the exact installed Skill roots."""
    config = load_json(source)
    if not isinstance(config, dict):
        raise ValueError("OpenCode config must be a JSON object")
    permissions = config.setdefault("permission", {})
    if not isinstance(permissions, dict):
        raise ValueError("OpenCode permission must be an object")
    permissions["external_directory"] = {
        f"{path.resolve().as_posix()}/**": "allow"
        for path in bundle_skill_paths(config_dir)
    }
    mcp = config.setdefault("mcp", {})
    if not isinstance(mcp, dict):
        raise ValueError("OpenCode mcp must be an object")
    mcp["analysis"] = render_opencode_mcp_fragment(
        config_dir / "analyze-repo-for-kubernetes" / "runtime"
    )["mcp"]["analysis"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def profile_environment(
    mode: str,
    config: Path | None,
    config_dir: Path | None,
    home: Path,
    log_root: Path,
) -> dict[str, str]:
    environment = os.environ.copy()
    if mode == "isolated":
        if config is None or config_dir is None:
            raise ValueError("isolated mode requires a config and config directory")
        environment.update(
            {
                "HOME": str(home.resolve()),
                "OPENCODE_CONFIG": str(config.resolve()),
                "OPENCODE_CONFIG_DIR": str(config_dir.resolve()),
                "XDG_CONFIG_HOME": str((home / ".config").resolve()),
                "XDG_DATA_HOME": str((home / ".local" / "share").resolve()),
                "XDG_STATE_HOME": str((home / ".local" / "state").resolve()),
                "XDG_CACHE_HOME": str((home / ".cache").resolve()),
            }
        )
    else:
        # User mode deliberately inherits the user's configuration and Skill
        # discovery variables. The runner only captures them in the trace.
        return environment
    environment["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
    environment["OPENCODE_TRACE_LOG_ROOT"] = str(log_root.resolve())
    return environment


def profile_paths(
    mode: str,
    target: Path,
    home: Path,
    config: Path | None,
    config_dir: Path | None,
    output_dir: Path | None,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "cwd": str(target.resolve()),
        "repository_root": str(target.resolve()),
        "home": str(home.resolve()),
        "opencode_config": str(config.resolve()) if config else None,
        "opencode_config_dir": str(config_dir.resolve()) if config_dir else None,
        "skill_discovery_paths": [
            str(path.resolve()) for path in standard_skill_paths(home, config_dir)
        ],
        "agent_paths": [
            str(path.resolve()) for path in standard_agent_paths(home, config_dir)
        ],
        "command_path": (
            f"{config.resolve()}#command.analyze-repo-for-kubernetes" if config else None
        ),
        "log_root": str((home / ".local" / "state" / "opencode").resolve()),
        "captured_log_root": str(output_dir.resolve()) if output_dir else None,
    }


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


def progressive_disclosure_errors(events: list[dict[str, Any]]) -> list[str]:
    """Reject deterministic traces that load an undeclared future stage or reference."""
    errors: list[str] = []
    loaded: list[str] = []
    current_skill: str | None = None
    accepted_discovery = False
    accepted_execution = False
    accepted_relationships = False
    accepted_boundaries = False
    for event in events:
        tool = event.get("tool")
        arguments = event.get("input", {})
        result = event.get("result", event.get("output", {}))
        if tool == "submit_discovery":
            if current_skill != "analyze-k8s-discovery":
                errors.append("discovery submit was called outside the discovery Skill")
            elif isinstance(result, dict) and result.get("status") == "accepted":
                accepted_discovery = True
        if tool == "submit_execution":
            if current_skill != "analyze-k8s-execution":
                errors.append("execution submit was called outside the execution Skill")
            elif isinstance(result, dict) and result.get("status") == "accepted":
                accepted_execution = True
        if tool == "submit_relationships":
            if current_skill != "analyze-k8s-relationships":
                errors.append("relationships submit was called outside the relationships Skill")
            elif isinstance(result, dict) and result.get("status") == "accepted":
                accepted_relationships = True
        if tool == "submit_boundaries":
            if current_skill != "analyze-k8s-boundaries":
                errors.append("boundaries submit was called outside the boundaries Skill")
            elif isinstance(result, dict) and result.get("status") == "accepted":
                accepted_boundaries = True
        if tool == "skill" and isinstance(arguments, dict):
            skill_id = arguments.get("name")
            if skill_id not in BUNDLE_SKILL_IDS:
                errors.append("undeclared Skill load")
                continue
            loaded.append(skill_id)
            current_skill = skill_id
            if loaded[0] != SKILL_ID:
                errors.append("dispatcher must be the first loaded Skill")
            if len(loaded) == 2 and loaded[1] != "analyze-k8s-discovery":
                errors.append("only discovery may follow the start handoff")
            if len(loaded) == 3 and loaded[2] != "analyze-k8s-execution":
                errors.append("only an accepted discovery handoff may load execution")
            if len(loaded) == 3 and not accepted_discovery:
                errors.append("execution was loaded without an accepted discovery handoff")
            if len(loaded) == 4 and loaded[3] != "analyze-k8s-relationships":
                errors.append("only an accepted execution handoff may load relationships")
            if len(loaded) == 4 and not accepted_execution:
                errors.append("relationships was loaded without an accepted execution handoff")
            if len(loaded) == 5 and loaded[4] != "analyze-k8s-boundaries":
                errors.append("only an accepted relationships handoff may load boundaries")
            if len(loaded) == 5 and not accepted_relationships:
                errors.append("boundaries was loaded without an accepted relationships handoff")
            if len(loaded) == 6 and loaded[5] != "analyze-k8s-contracts":
                errors.append("only an accepted boundaries handoff may load contracts")
            if len(loaded) == 6 and not accepted_boundaries:
                errors.append("contracts was loaded without an accepted boundaries handoff")
            if len(loaded) > 6:
                errors.append("later skeletal stages must stop before another Skill loads")
        if tool in {"read", "skill"} and isinstance(arguments, dict):
            path = arguments.get("path") or arguments.get("filePath")
            if isinstance(path, str) and "analyze-k8s-" in path:
                stage_path = next((skill_id for skill_id in BUNDLE_SKILL_IDS[1:] if skill_id in path), None)
                if stage_path is not None and stage_path != current_skill:
                    errors.append("future Skill reference read")
    return errors


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


def is_analysis_case(case: dict[str, Any]) -> bool:
    return case.get("acceptance_type") == "analysis" or "report_mode" in case


def case_command(case: dict[str, Any], use_command: bool = True) -> str | None:
    """Return the slash command a case invokes, if it declares one.

    A case opts into the installed custom command by naming it. Cases that
    exercise the natural-language entry deliberately omit the key and must not
    receive an implicit `--command`.
    """
    name = case.get("command")
    if not use_command or not isinstance(name, str) or not name:
        return None
    return name


def collect_tool_calls(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    known = {"read", "glob", "grep", "list", "bash", "skill", "edit", "write", "patch", "task"}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            tool = value.get("tool") or value.get("name")
            if isinstance(tool, str) and tool in known:
                state = value.get("state") if isinstance(value.get("state"), dict) else {}
                call_input = value.get("input", value.get("args"))
                if call_input is None:
                    call_input = state.get("input", {})
                call = {"tool": tool, "input": redact(call_input)}
                if state.get("status") is not None:
                    call["status"] = state["status"]
                if state.get("error") is not None:
                    call["error"] = redact(state["error"])
                calls.append(call)
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
    project: ProjectMetadata | None = None,
    profile: dict[str, Any] | None = None,
    repository: dict[str, Any] | None = None,
    config_audit: dict[str, Any] | None = None,
    command_agent: str | None = None,
) -> dict[str, Any]:
    project = project or load_project_metadata(ROOT)
    calls = collect_tool_calls(events)
    reads: list[str] = []
    for call in calls:
        if call.get("tool") != "read":
            continue
        for path in re.findall(
            r"(?:SKILL\.md|references/[A-Za-z0-9._/-]+\.md|assets/[A-Za-z0-9._/-]+\.md)",
            " ".join(strings_in(call.get("input", {}))),
        ):
            if path not in reads:
                reads.append(path)
    skill_loaded = any(
        call.get("tool") == "skill" and project.skill_id in strings_in(call.get("input", {}))
        for call in calls
    )
    if skill_loaded and "SKILL.md" not in reads:
        reads.insert(0, "SKILL.md")
    denials: list[dict[str, str]] = []
    for call in calls:
        if call.get("status") == "error":
            denials.append({"event": f"{call.get('tool')}: {call.get('error', 'tool error')}"})
    for event in events:
        text = event_text(event)
        lowered = text.lower()
        if "permission" in lowered and any(word in lowered for word in ("deny", "denied", "reject", "rejected")):
            denials.append({"event": text[:500]})
    final_output = "\n".join(
        event_content(event)
        for event in events
        if event.get("type") in {"text", "message", "assistant"}
    ).strip()
    if not final_output:
        final_output = stdout.strip()
    trace = {
        "status": status,
        "reason": reason,
        "returncode": returncode,
        "command": command,
        "skill": {"id": project.skill_id, "description": metadata.get("description", ""), "loaded": skill_loaded},
        "agent": project.agent_id,
        "events": events,
        "tool_calls": calls,
        "supporting_reads": reads,
        "permission_denials": denials,
        "final_output": redact(final_output[-12000:]),
    }
    if profile is not None:
        trace["profile"] = profile
    if repository is not None:
        trace["repository"] = repository
    if config_audit is not None:
        trace["config_audit"] = config_audit
    if command_agent is not None:
        trace["command_agent"] = command_agent
    return trace


def extract_json_object(raw_output: str) -> str:
    """Recover a JSON object from the Agent's final message.

    The Agent is instructed to return raw JSON with no fence, but this stays
    tolerant of a stray ```json fence or surrounding whitespace/prose so a
    close-but-imperfect response still gets a precise parse error instead of
    an opaque one.
    """
    text = raw_output.strip()
    fence = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


RENDERERS = {"summary": render_summary, "detailed": render_detailed}


def extract_markdown_report(raw_output: str, *, mode: str) -> str:
    """Return the final agent-authored Markdown report from an interactive trace."""
    heading = "# Kubernetes 설계 입력 요약" if mode == "summary" else "# Kubernetes 설계 입력 상세 평가"
    start = raw_output.rfind(heading)
    if start < 0:
        raise ValueError(f"{mode.capitalize()} final output is missing required Markdown heading: {heading}")
    return raw_output[start:].strip() + "\n"


def retain_agent_markdown(raw_output: str, output_dir: Path, repository_root: Path, *, mode: str = "summary") -> str:
    """Validate the final Markdown emitted after in-session MCP finalization.

    This is intentionally separate from the legacy JSON renderer. Interactive
    OpenCode acceptance must validate the assistant's own final Markdown and
    must not depend on an out-of-session renderer or report finalizer.
    """
    label = mode.capitalize()
    markdown = extract_markdown_report(raw_output, mode=mode)
    report = output_dir / "report.md"
    report.write_text(markdown, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate_report.py"), str(report), "--mode", mode, "--repo-root", str(repository_root)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode:
        raise ValueError(result.stdout.strip() or result.stderr.strip() or f"{label} Markdown validation failed")
    return report.read_text(encoding="utf-8")


def retain_report_markdown(raw_output: str, output_dir: Path, repository_root: Path, *, mode: str = "summary") -> str:
    """Render, validate, and finalize the Agent's Summary or Detailed JSON.

    Per ADR-2026-07-30-004 / ADR-2026-08-07-001 (Summary) and VS-024
    (Detailed): the Agent returns JSON only; this is the pipeline's only
    producer of user-facing Markdown for either mode.
    """
    label = mode.capitalize()
    payload_text = extract_json_object(raw_output)
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} output is not valid JSON: {error}") from error
    (output_dir / "payload.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    try:
        markdown = RENDERERS[mode](payload)
    except ValueError as error:
        raise ValueError(f"{label} JSON failed to render: {error}") from error
    report = output_dir / "report.md"
    report.write_text(markdown, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate_report.py"), str(report), "--mode", mode, "--repo-root", str(repository_root)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode:
        raise ValueError(result.stdout.strip() or result.stderr.strip() or f"{label} Markdown validation failed")
    finalize_returncode = finalize_receipt(report, repository_root, mode=mode)
    if finalize_returncode:
        raise ValueError(f"{label} Markdown receipt finalization failed")
    return report.read_text(encoding="utf-8")


def retain_summary_markdown(raw_output: str, output_dir: Path, repository_root: Path) -> str:
    return retain_report_markdown(raw_output, output_dir, repository_root, mode="summary")


def retain_detailed_markdown(raw_output: str, output_dir: Path, repository_root: Path) -> str:
    return retain_report_markdown(raw_output, output_dir, repository_root, mode="detailed")


def continue_session(
    session_id: str,
    message: str,
    executable: str,
    target: Path,
    environment: dict[str, str],
    agent_id: str,
    runner: CommandRunner = subprocess.run,
    timeout: float = 180,
    pure: bool = True,
) -> str:
    """Send a follow-up message in an existing session and return its final text output."""
    command = [executable, "run", "--format", "json", "--agent", agent_id, "--dir", str(target), "--session", session_id, "--print-logs", "--log-level", "DEBUG"]
    if pure:
        command.insert(1, "--pure")
    if message.startswith("-"):
        command.append("--")
    command.append(message)
    result = runner(
        command,
        cwd=target,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=timeout,
    )
    events = event_lines(result.stdout)
    final_output = "\n".join(
        event_content(event) for event in events if event.get("type") in {"text", "message", "assistant"}
    ).strip()
    return final_output or result.stdout.strip()


REPAIR_CONTRACT_FIELDS = {
    "summary": "schema_version, mode, scope, components, dependencies, excluded_items, "
    "missing_inputs, evidence, design_input_verdict",
    "detailed": "schema_version, mode, scope, components, dependencies, excluded_items, "
    "missing_inputs, evidence, design_input_verdict, deployment_basis, configuration_details",
}


def retain_report_markdown_with_repair(
    trace: dict[str, Any],
    output_dir: Path,
    repository_root: Path,
    *,
    mode: str = "summary",
    executable: str,
    target: Path,
    environment: dict[str, str],
    agent_id: str,
    runner: CommandRunner = subprocess.run,
    timeout: float = 180,
    pure: bool = True,
    max_repairs: int = 2,
) -> str:
    """Validate final agent Markdown and request one in-session repair if needed."""
    label = mode.capitalize()
    raw_output = str(trace["final_output"])
    attempts: list[str] = []
    for attempt in range(max_repairs + 1):
        try:
            markdown = retain_agent_markdown(raw_output, output_dir, repository_root, mode=mode)
            if attempts:
                trace["repair_attempts"] = attempts
            return markdown
        except ValueError as error:
            attempts.append(str(error))
            session_id = trace.get("session_id")
            if attempt >= max_repairs or not session_id:
                trace["repair_attempts"] = attempts
                raise
            repair_message = (
                "방금 만든 Markdown 보고서에 문제가 있습니다: "
                f"{error}\n\n"
                f"필요한 근거를 다시 확인해 해당 부분만 정확히 고친 뒤, {label} Markdown "
                "보고서 전체를 다시 출력하세요. 코드 펜스나 보고서 밖 설명은 출력하지 않습니다."
            )
            try:
                raw_output = continue_session(
                    session_id,
                    repair_message,
                    executable,
                    target,
                    environment,
                    agent_id,
                    runner=runner,
                    timeout=timeout,
                    pure=pure,
                )
            except subprocess.TimeoutExpired as timeout_error:
                attempts.append(f"repair session timed out: {timeout_error}")
                trace["repair_attempts"] = attempts
                raise ValueError(f"repair session timed out: {timeout_error}") from timeout_error


def retain_summary_markdown_with_repair(trace: dict[str, Any], output_dir: Path, repository_root: Path, **kwargs: Any) -> str:
    return retain_report_markdown_with_repair(trace, output_dir, repository_root, mode="summary", **kwargs)


def retain_detailed_markdown_with_repair(trace: dict[str, Any], output_dir: Path, repository_root: Path, **kwargs: Any) -> str:
    return retain_report_markdown_with_repair(trace, output_dir, repository_root, mode="detailed", **kwargs)


def extract_report(trace: dict[str, Any]) -> dict[str, Any] | None:
    candidates: list[str] = [str(trace.get("final_output", ""))]
    for event in trace.get("events", []):
        if isinstance(event, dict):
            candidates.extend((event_content(event), event_text(event)))
    candidates = [candidate for text in candidates for candidate in (text, *re.findall(
        r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL
    ))]
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("schema_version") == "1.0":
            return payload
    return None


def unavailable_trace(
    case: dict[str, Any],
    reason: str,
    metadata: dict[str, str],
    project: ProjectMetadata | None = None,
    profile: dict[str, Any] | None = None,
    repository: dict[str, Any] | None = None,
    config_audit_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return normalize_trace(
        [],
        "",
        "",
        127,
        [],
        metadata,
        "UNAVAILABLE",
        reason,
        project,
        profile=profile,
        repository=repository,
        config_audit=config_audit_result,
    ) | {"case_id": case["id"], "query": case["query"]}


def executable_path(opencode: str) -> str | None:
    executable = shutil.which(opencode, path=os.environ.get("PATH")) if Path(opencode).name == opencode else opencode
    if not executable or not Path(executable).exists():
        return None
    return executable


def run_debug_probe(
    name: str,
    executable: str,
    target: Path,
    environment: dict[str, str],
    output_dir: Path,
    runner: CommandRunner = subprocess.run,
    timeout: float = 60,
    pure: bool = True,
) -> dict[str, Any]:
    command = [executable, "debug", name, "--print-logs", "--log-level", "DEBUG"]
    if pure:
        command.append("--pure")
    if name == "agent":
        command.append(AGENT_ID)
    try:
        result = runner(
            command,
            cwd=target,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=timeout,
        )
        output = {
            "returncode": result.returncode,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
        }
        status = "PASS" if result.returncode == 0 else "FAIL"
    except subprocess.TimeoutExpired as error:
        output = {
            "returncode": 124,
            "stdout": output_text(error.stdout),
            "stderr": output_text(error.stderr),
        }
        status = "UNAVAILABLE"
        output["reason"] = f"debug {name} timed out: {error}"
    except OSError as error:
        output = {"returncode": 127, "stdout": "", "stderr": str(error)}
        status = "UNAVAILABLE"
        output["reason"] = f"debug {name} could not execute: {error}"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{name}.stdout.log").write_text(
        redact(output.get("stdout", "")), encoding="utf-8"
    )
    (output_dir / f"{name}.stderr.log").write_text(
        redact(output.get("stderr", "")), encoding="utf-8"
    )
    return {
        "name": name,
        "status": status,
        "command": command,
        "cwd": str(target.resolve()),
        "returncode": output["returncode"],
        "stdout_file": str((output_dir / f"{name}.stdout.log").resolve()),
        "stderr_file": str((output_dir / f"{name}.stderr.log").resolve()),
        "stdout": redact(output.get("stdout", "")),
        "stderr": redact(output.get("stderr", "")),
        **({"reason": output["reason"]} if "reason" in output else {}),
    }


def run_debug_probes(
    executable: str | None,
    target: Path,
    environment: dict[str, str],
    output_dir: Path,
    runner: CommandRunner = subprocess.run,
    timeout: float = 60,
    pure: bool = True,
) -> dict[str, Any]:
    if executable is None:
        return {
            "status": "UNAVAILABLE",
            "reason": "OpenCode executable not found",
            "probes": [],
        }
    probes = [
        run_debug_probe(name, executable, target, environment, output_dir, runner, timeout, pure)
        for name in ("config", "startup", "skill", "agent")
    ]
    return {
        "status": "PASS" if all(probe["status"] == "PASS" for probe in probes) else "FAIL",
        "probes": probes,
    }


def run_interactive_probe(
    executable: str | None,
    target: Path,
    environment: dict[str, str],
    output_dir: Path,
    pure: bool,
    query: str = "현재 저장소를 Kubernetes 이관 관점에서 분석해줘.",
    runner: CommandRunner = subprocess.run,
    timeout: float = 180,
) -> dict[str, Any]:
    if executable is None:
        return {"status": "UNAVAILABLE", "reason": "OpenCode executable not found"}
    command = [
        executable,
        "run",
        "--interactive",
        "--agent",
        AGENT_ID,
        "--dir",
        str(target.resolve()),
        "--print-logs",
        "--log-level",
        "DEBUG",
        "--command",
        "analyze-repo-for-kubernetes",
    ]
    if pure:
        command.insert(2, "--pure")
    try:
        result = runner(
            command,
            cwd=target,
            env=environment,
            input=query + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=timeout,
        )
        status = "PASS" if result.returncode == 0 else "FAIL"
        payload: dict[str, Any] = {
            "returncode": result.returncode,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
        }
    except subprocess.TimeoutExpired as error:
        status = "UNAVAILABLE"
        payload = {
            "returncode": 124,
            "stdout": output_text(error.stdout),
            "stderr": output_text(error.stderr),
            "reason": f"interactive OpenCode timed out: {error}",
        }
    except OSError as error:
        status = "UNAVAILABLE"
        payload = {"returncode": 127, "stdout": "", "stderr": str(error), "reason": str(error)}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "stdout.log").write_text(redact(payload.get("stdout", "")), encoding="utf-8")
    (output_dir / "stderr.log").write_text(redact(payload.get("stderr", "")), encoding="utf-8")
    return {
        "status": status,
        "command": command,
        "cwd": str(target.resolve()),
        "returncode": payload["returncode"],
        "stdout_file": str((output_dir / "stdout.log").resolve()),
        "stderr_file": str((output_dir / "stderr.log").resolve()),
        "reason": payload.get("reason"),
    }


def config_audit(config: Path | None, agent_path: Path | None, expected_skill_path: Path | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "config_path": str(config.resolve()) if config else None,
        "agent_path": str(agent_path.resolve()) if agent_path else None,
        "expected_skill_path": str(expected_skill_path.resolve()) if expected_skill_path else None,
        "command_registered": False,
        "command_agent": None,
        "allowed_skill_ids": [],
        "permission": {},
        "model": None,
        "provider": None,
        "errors": [],
    }
    if config is not None and config.is_file():
        try:
            payload = load_json(config)
            command = payload.get("command", {}).get("analyze-repo-for-kubernetes", {})
            result["command_registered"] = isinstance(command, dict)
            result["command_agent"] = command.get("agent") if isinstance(command, dict) else None
            permissions = payload.get("permission", {})
            result["permission"] = permissions
            result["model"] = payload.get("model")
            model = payload.get("model")
            result["provider"] = model.split("/", 1)[0] if isinstance(model, str) and "/" in model else None
            skill_permissions = permissions.get("skill", {}) if isinstance(permissions, dict) else {}
            if isinstance(skill_permissions, dict):
                result["allowed_skill_ids"] = sorted(
                    key for key, value in skill_permissions.items() if key != "*" and value == "allow"
                )
        except (OSError, json.JSONDecodeError, AttributeError) as error:
            result["errors"].append(f"config could not be parsed: {error}")
    else:
        result["errors"].append("config file is missing")
    if agent_path is not None and not agent_path.is_file():
        result["errors"].append("agent file is missing")
    result["command_agent_matches"] = result["command_agent"] == AGENT_ID
    result["skill_path_exists"] = bool(expected_skill_path and expected_skill_path.is_dir())
    return result


def run_case(
    case: dict[str, Any],
    config: Path | None,
    opencode: str,
    root: Path,
    home: Path,
    config_dir: Path | None,
    repository_root: Path | None = None,
    model: str | None = None,
    timeout: float = 180,
    runner: CommandRunner = subprocess.run,
    mode: str = "isolated",
    profile: dict[str, Any] | None = None,
    config_audit_result: dict[str, Any] | None = None,
    artifact_dir: Path | None = None,
    use_command: bool = True,
    pure: bool = True,
) -> dict[str, Any]:
    metadata = parse_frontmatter(root / "SKILL.md")
    project = load_project_metadata(root)
    executable = executable_path(opencode)
    target = (repository_root or (root / case["repository_fixture"]).resolve()).resolve()
    profile = profile or {
        "mode": mode,
        "cwd": str(target),
        "repository_root": str(target),
    }
    baseline = repository_baseline(target)
    if not executable:
        return unavailable_trace(
            case,
            "OpenCode executable not found",
            metadata,
            project,
            profile=profile,
            repository=repository_integrity(target, baseline),
            config_audit_result=config_audit_result,
        )

    command = [
        executable,
        "run",
        "--format",
        "json",
        "--agent",
        project.agent_id,
        "--dir",
        str(target.resolve()),
        "--print-logs",
        "--log-level",
        "DEBUG",
    ]
    if pure:
        command.insert(2, "--pure")
    if model:
        command.extend(["--model", model])
    if case_command(case, use_command):
        command.extend(["--command", case_command(case, use_command)])
    query = case["query"]
    if query.startswith("-"):
        command.append("--")
    if query:
        command.append(query)
    config_path = config.resolve() if config else None
    config_dir_path = config_dir.resolve() if config_dir else None
    environment = profile_environment(
        mode,
        config_path,
        config_dir_path,
        home,
        artifact_dir or target,
    )
    started = time.monotonic()
    try:
        result = runner(
            command,
            cwd=target,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
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
            project,
            profile=profile | {"environment": {key: environment.get(key) for key in ("HOME", "OPENCODE_CONFIG", "OPENCODE_CONFIG_DIR")}},
            repository=repository_integrity(target, baseline),
            config_audit=config_audit_result,
            command_agent=AGENT_ID if case_command(case, use_command) else None,
        )
        trace.update({"case_id": case["id"], "query": case["query"]})
        trace["elapsed_seconds"] = round(time.monotonic() - started, 6)
        if artifact_dir is not None:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / "stdout.log").write_text(redact(partial_stdout), encoding="utf-8")
            (artifact_dir / "stderr.log").write_text(redact(partial_stderr), encoding="utf-8")
            trace["stdout_file"] = str((artifact_dir / "stdout.log").resolve())
            trace["stderr_file"] = str((artifact_dir / "stderr.log").resolve())
        return trace
    except OSError as error:
        return unavailable_trace(
            case,
            f"OpenCode could not complete: {error}",
            metadata,
            project,
            profile=profile,
            repository=repository_integrity(target, baseline),
            config_audit_result=config_audit_result,
        )

    events = event_lines(result.stdout)
    elapsed_seconds = round(time.monotonic() - started, 6)
    trace = normalize_trace(
        events,
        result.stdout,
        result.stderr,
        result.returncode,
        command,
        metadata,
        "PASS" if result.returncode == 0 else "FAIL",
        None if result.returncode == 0 else "OpenCode returned a nonzero exit code",
        project,
        profile=profile | {"environment": {key: environment.get(key) for key in ("HOME", "OPENCODE_CONFIG", "OPENCODE_CONFIG_DIR")}},
        repository=repository_integrity(target, baseline),
        config_audit=config_audit_result,
        command_agent=AGENT_ID if case_command(case, use_command) else None,
    )
    trace.update({"case_id": case["id"], "query": case["query"]})
    trace["elapsed_seconds"] = elapsed_seconds
    trace["session_id"] = next((event.get("sessionID") for event in events if event.get("sessionID")), None)
    report = extract_report(trace)
    if report is not None:
        trace["report_file"] = "report.json"
        trace["report"] = report
    trace["command_agent_matches"] = (
        trace.get("command_agent") == AGENT_ID
        if trace.get("command_agent") is not None
        else config_audit_result.get("command_agent_matches") if config_audit_result else None
    )
    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / "stdout.log").write_text(redact(result.stdout), encoding="utf-8")
        (artifact_dir / "stderr.log").write_text(redact(result.stderr), encoding="utf-8")
        trace["stdout_file"] = str((artifact_dir / "stdout.log").resolve())
        trace["stderr_file"] = str((artifact_dir / "stderr.log").resolve())
    return trace


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenCode Skill acceptance adapter")
    parser.add_argument(
        "--mode",
        choices=("user", "isolated"),
        default="isolated",
        help="user는 전역 OpenCode 환경을 사용하고 isolated는 임시 환경을 구성합니다.",
    )
    parser.add_argument("--config", type=Path, help="isolated mode에서 복사할 OpenCode config")
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--opencode", default=DEFAULT_OPENCODE)
    parser.add_argument("--model", help="선택적 provider/model 지정")
    parser.add_argument("--timeout", type=float, default=180, help="case별 OpenCode timeout 초")
    parser.add_argument("--debug-timeout", type=float, default=60, help="debug probe별 timeout 초")
    parser.add_argument("--repeat", type=int, default=1, help="각 case를 반복 실행할 횟수")
    parser.add_argument(
        "--skip-debug",
        action="store_true",
        help="debug config/startup/skill/agent probe를 생략합니다.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="profile별 대표 interactive 실행을 한 번 수행하고 결과를 보존합니다.",
    )
    parser.add_argument(
        "--no-command",
        action="store_true",
        help="analysis case에서 custom command 호출을 생략합니다.",
    )
    parser.add_argument(
        "--pure",
        action="store_true",
        help="user mode에서도 --pure를 전달합니다. isolated mode는 항상 pure입니다.",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
        help="실행할 case ID (여러 번 지정 가능)",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        help="모든 acceptance case를 이 read-only Repository 경로에서 실행합니다.",
    )
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    payload = load_json(args.cases)
    cases = payload.get("cases", []) if isinstance(payload, dict) else []
    if args.case_ids:
        selected = set(args.case_ids)
        cases = [case for case in cases if case.get("id") in selected]
        missing = selected - {case.get("id") for case in cases}
        if missing:
            parser.error(f"unknown case ID: {', '.join(sorted(missing))}")
    output_dir = args.output_dir.resolve()
    target_for_scope = args.repository_root.resolve() if args.repository_root else None
    if target_for_scope is not None and path_is_within(output_dir, target_for_scope):
        parser.error("--output-dir must be outside --repository-root")
    output_dir.mkdir(parents=True, exist_ok=True)
    source_config = (args.config or ROOT / "runtime/opencode.json").resolve()
    if args.mode == "user" and args.config is not None:
        parser.error("user mode uses the user's global OpenCode configuration; omit --config")
    if args.mode == "isolated" and not source_config.is_file():
        parser.error(f"isolated config does not exist: {source_config}")

    with tempfile.TemporaryDirectory(prefix="opencode-acceptance-") as temporary:
        temporary_root = Path(temporary)
        isolated = args.mode == "isolated"
        home = temporary_root / "home" if isolated else Path(os.environ.get("HOME", str(Path.home())))
        config_dir = temporary_root / "config" if isolated else Path(
            os.environ.get("OPENCODE_CONFIG_DIR", str(home / ".config" / "opencode"))
        )
        config_path: Path | None = None
        installed_skill: Path | None = None
        agent_path: Path | None = None
        installed_bundle: Path | None = None
        if isolated:
            assert config_dir is not None
            installed_skill = config_dir / "skills" / SKILL_ID
            installed_bundle = copy_bundle(ROOT, temporary_root / "bundle")
            install_bundle(installed_bundle, config_dir)
            config_path = temporary_root / "runtime" / "opencode.json"
            isolated_config_bundle(source_config, config_path, config_dir)
            agent_path = config_dir / "agent" / f"{AGENT_ID}.md"
            home.mkdir(parents=True, exist_ok=True)
        else:
            # User mode is intentionally read-only with respect to all config
            # and Skill paths. No .opencode directory is created or copied.
            home = home.resolve()
            configured = os.environ.get("OPENCODE_CONFIG")
            config_path = Path(configured).resolve() if configured else config_dir / "opencode.json"

        fixed_target = target_for_scope
        profile_target = fixed_target
        if profile_target is None and cases:
            profile_target = (ROOT / cases[0]["repository_fixture"]).resolve()
        if profile_target is None:
            parser.error("cases must contain a repository fixture or --repository-root is required")
        if path_is_within(output_dir, profile_target):
            parser.error("--output-dir must be outside the application repository")
        log_root = output_dir / "logs"
        environment = profile_environment(args.mode, config_path, config_dir, home, log_root)
        paths = profile_paths(args.mode, profile_target, home, config_path, config_dir, output_dir)
        audit = (
            discovery_audit_bundle(installed_bundle, config_dir, profile_target, args.mode)
            if installed_bundle is not None
            else discovery_audit(ROOT, home, config_dir, profile_target, args.mode)
        )
        audit["config"] = config_audit(config_path, agent_path, installed_skill)
        paths["model"] = args.model or audit["config"].get("model")
        paths["provider"] = audit["config"].get("provider")
        executable = executable_path(args.opencode)
        (output_dir / "run-metadata.json").write_text(
            json.dumps(
                {
                    "mode": args.mode,
                    "cwd": str(profile_target),
                    "HOME": environment.get("HOME"),
                    "OPENCODE_CONFIG": environment.get("OPENCODE_CONFIG"),
                    "OPENCODE_CONFIG_DIR": environment.get("OPENCODE_CONFIG_DIR"),
                    "skill_discovery_paths": paths["skill_discovery_paths"],
                    "agent_path": paths["agent_paths"],
                    "command_path": paths["command_path"],
                    "repository_root": str(profile_target),
                    "output_dir": str(output_dir),
                    "config_audit": audit,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        if args.skip_debug:
            debug = {"status": "SKIP", "reason": "--skip-debug", "probes": []}
        else:
            debug = run_debug_probes(
                executable,
                profile_target,
                environment,
                output_dir / "debug",
                timeout=args.debug_timeout,
                pure=isolated or args.pure,
            )
        (output_dir / "debug.json").write_text(
            json.dumps(redact(debug), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if args.interactive:
            interactive = run_interactive_probe(
                executable,
                profile_target,
                environment,
                output_dir / "interactive",
                pure=isolated or args.pure,
                timeout=args.timeout,
            )
        else:
            interactive = {"status": "SKIP", "reason": "--interactive not requested"}
        (output_dir / "interactive.json").write_text(
            json.dumps(redact(interactive), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        for repeat in range(1, args.repeat + 1):
            for case in cases:
                case_dir = output_dir / (f"repeat-{repeat:02d}" if args.repeat > 1 else "") / case["id"]
                case_dir.mkdir(parents=True, exist_ok=True)
                case_profile = (
                    paths
                    if fixed_target is not None
                    else profile_paths(
                        args.mode,
                        (ROOT / case["repository_fixture"]).resolve(),
                        home,
                        config_path,
                        config_dir,
                        output_dir,
                    )
                )
                case_profile["model"] = paths["model"]
                case_profile["provider"] = paths["provider"]
                trace = run_case(
                    case,
                    config_path,
                    args.opencode,
                    ROOT,
                    home,
                    config_dir,
                    repository_root=fixed_target,
                    model=args.model,
                    timeout=args.timeout,
                    mode=args.mode,
                    profile=case_profile,
                    config_audit_result=audit["config"],
                    artifact_dir=case_dir,
                    use_command=not args.no_command,
                    pure=isolated or args.pure,
                )
                report_mode = case.get("expected_behavior", {}).get("report_mode")
                if trace["status"] == "PASS" and report_mode in {"summary", "detailed"}:
                    try:
                        report_target = fixed_target or (ROOT / case["repository_fixture"]).resolve()
                        trace["final_output"] = retain_report_markdown_with_repair(
                            trace,
                            case_dir,
                            report_target,
                            mode=report_mode,
                            executable=executable,
                            target=report_target,
                            environment=environment,
                            agent_id=AGENT_ID,
                            timeout=args.timeout,
                            pure=isolated or args.pure,
                        )
                        trace["report_file"] = "report.md"
                    except ValueError as error:
                        trace["markdown_error"] = str(error)
                        trace["status"] = "FAIL"
                        trace["reason"] = f"{report_mode.capitalize()} Markdown validation failed"
                (case_dir / "trace.json").write_text(
                    json.dumps(redact(trace), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                report = trace.get("report")
                if isinstance(report, dict):
                    (case_dir / "report.json").write_text(
                        json.dumps(redact(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                print(
                    f"{args.mode}/repeat-{repeat:02d}/{case['id']}: {trace['status']}"
                    + (f" ({trace['reason']})" if trace.get("reason") else "")
                )
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
