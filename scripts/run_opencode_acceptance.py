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
import sqlite3
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
        relative = Path(entry)
        # This legacy dispatcher-only fixture is not the seven-Skill bundle.
        # Flatten the otherwise redundant `runtime/` prefix for stage files so
        # its Windows temporary path remains below MAX_PATH.
        target = (
            destination / "stage-skills" / Path(*relative.parts[2:])
            if relative.parts[:2] == ("runtime", "stage-skills")
            else destination / relative
        )
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
    marker = '"__INSTALLED_SKILL_ROOTS__": allow'
    if text.count(marker) != 2:
        raise ValueError("agent source must contain read and external-directory Skill root markers")
    exact_rule = f'"{skill_path.resolve().as_posix()}/**": allow'
    text = text.replace(marker, exact_rule)
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


def isolated_config_bundle(
    source: Path,
    destination: Path,
    config_dir: Path,
    *,
    runtime_python: str | None = None,
) -> None:
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
    fragment = render_opencode_mcp_fragment(config_dir / "analyze-repo-for-kubernetes" / "runtime")
    if runtime_python is not None:
        fragment["mcp"]["analysis"]["command"][0] = runtime_python
    mcp["analysis"] = fragment["mcp"]["analysis"]
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
    accepted_contracts = False
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
        if tool == "submit_contracts":
            if current_skill != "analyze-k8s-contracts":
                errors.append("contracts submit was called outside the contracts Skill")
            elif isinstance(result, dict) and result.get("status") == "accepted":
                accepted_contracts = True
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
            if len(loaded) == 7 and loaded[6] != "analyze-k8s-finalize":
                errors.append("only an accepted contracts handoff may load finalize")
            if len(loaded) == 7 and not accepted_contracts:
                errors.append("finalize was loaded without an accepted contracts handoff")
            if len(loaded) > 7:
                errors.append("no additional Skill may load after finalize")
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


STATIC_MCP_TOOL_SEQUENCE = (
    ("start_analysis", "accepted"),
    ("submit_discovery", "accepted"),
    ("submit_execution", "accepted"),
    ("submit_relationships", "accepted"),
    ("submit_boundaries", "accepted"),
    ("submit_contracts", "accepted"),
    ("finalize_analysis", "finalized"),
)
STATIC_MCP_PATH_STYLES = {"absolute", "command-relative"}


def load_static_mcp_cases(path: Path) -> list[dict[str, Any]]:
    """Load the provider-backed case manifest without inspecting a target."""
    payload = load_json(path)
    if not isinstance(payload, dict) or payload.get("suite") != "static-mcp-opencode":
        raise ValueError("static MCP case manifest has an invalid suite")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not all(isinstance(case, dict) for case in cases):
        raise ValueError("static MCP case manifest must contain cases")
    return cases


def load_static_mcp_golden_manifest(path: Path) -> dict[str, dict[str, Any]]:
    """Return sealed golden metadata indexed by case ID after digest validation."""
    payload = load_json(path)
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if payload.get("schema_version") != 1 or not isinstance(cases, list):
        raise ValueError("static MCP golden manifest is invalid")
    indexed: dict[str, dict[str, Any]] = {}
    for item in cases:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("static MCP golden manifest has an invalid case")
        golden_name = item.get("golden")
        expected_hash = item.get("sha256")
        golden = path.parent / golden_name if isinstance(golden_name, str) else None
        if golden is None or not golden.is_file() or not isinstance(expected_hash, str):
            raise ValueError(f"static MCP golden is unavailable for {item['id']}")
        if sha256_file(golden) != expected_hash:
            raise ValueError(f"static MCP golden hash mismatch for {item['id']}")
        if item["id"] in indexed:
            raise ValueError(f"duplicate static MCP golden case: {item['id']}")
        indexed[item["id"]] = item
    return indexed


def validate_static_mcp_cases(
    cases: list[dict[str, Any]], golden_cases: dict[str, dict[str, Any]],
) -> list[str]:
    """Validate the fixed six provider cases before opening an interactive session."""
    errors: list[str] = []
    expected_ids = set(golden_cases)
    observed_ids: set[str] = set()
    styles: set[str] = set()
    for case in cases:
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id:
            errors.append("case is missing an id")
            continue
        if case_id in observed_ids:
            errors.append(f"duplicate case id: {case_id}")
            continue
        observed_ids.add(case_id)
        sealed = golden_cases.get(case_id)
        if sealed is None:
            errors.append(f"case is not sealed by a golden: {case_id}")
            continue
        for field in ("target", "mode", "golden"):
            if case.get(field) != sealed.get(field):
                errors.append(f"case {case_id} does not match sealed {field}")
        target_path = case.get("target_path")
        style = case.get("path_style")
        if not isinstance(target_path, str) or not target_path:
            errors.append(f"case {case_id} is missing target_path")
        if style not in STATIC_MCP_PATH_STYLES:
            errors.append(f"case {case_id} has an invalid path_style")
        else:
            styles.add(style)
        if case.get("mode") not in {"summary", "detailed"}:
            errors.append(f"case {case_id} has an invalid mode")
        if not isinstance(case.get("command_directory"), str) or not case.get("command_directory"):
            errors.append(f"case {case_id} is missing command_directory")
    missing = expected_ids - observed_ids
    unexpected = observed_ids - expected_ids
    if missing:
        errors.append("missing sealed cases: " + ", ".join(sorted(missing)))
    if unexpected:
        errors.append("unexpected cases: " + ", ".join(sorted(unexpected)))
    if len(cases) != 6:
        errors.append("static MCP acceptance requires exactly six cases")
    if styles != STATIC_MCP_PATH_STYLES:
        errors.append("static MCP acceptance requires absolute and command-relative target paths")
    return errors


def static_mcp_command_prompt(case: dict[str, Any]) -> str:
    """Render the single user-invoked command with its explicit target selection."""
    target_path = case["target_path"]
    selected_mode = "Detailed" if case["mode"] == "detailed" else "Summary"
    prompt = f"/analyze-repo-for-kubernetes {target_path} {selected_mode}"
    return prompt


def static_mcp_command_keystrokes(case: dict[str, Any]) -> list[str]:
    """Enter a custom command only after OpenCode has loaded its command catalog."""
    prompt = static_mcp_command_prompt(case)
    return ["/", prompt.removeprefix("/"), "\r"]


def _tool_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    name = value.removeprefix("analysis_")
    return name


def _tool_result_status(value: Any) -> str | None:
    if isinstance(value, str):
        try:
            return _tool_result_status(json.loads(value))
        except json.JSONDecodeError:
            return None
    if not isinstance(value, dict):
        return None
    direct = value.get("status")
    if isinstance(direct, str):
        return direct
    for nested in ("result", "output", "structuredContent", "state"):
        status = _tool_result_status(value.get(nested))
        if status:
            return status
    return None


def static_mcp_transition_errors(tool_calls: list[dict[str, Any]]) -> list[str]:
    """Check the externally visible one-pass stage transition contract."""
    errors: list[str] = []
    for tool, expected_status in STATIC_MCP_TOOL_SEQUENCE:
        matches = [
            call for call in tool_calls
            if _tool_name(call.get("name", call.get("tool"))) == tool
            and _tool_result_status(call) == expected_status
        ]
        if len(matches) != 1:
            errors.append(f"{tool} must be {expected_status} exactly once")
    known_tools = {tool for tool, _ in STATIC_MCP_TOOL_SEQUENCE}
    seen = [_tool_name(call.get("name", call.get("tool"))) for call in tool_calls]
    sequence = [tool for tool in seen if tool in known_tools]
    if sequence != [tool for tool, _ in STATIC_MCP_TOOL_SEQUENCE]:
        errors.append("accepted static MCP tools are out of order or repeated")
    return errors


def _required_golden_citations(golden: Path) -> list[str]:
    text = golden.read_text(encoding="utf-8")
    findings = text.partition("## Required findings\n")[2].partition("## Required blockers and unknowns")[0]
    citations = re.findall(
        r"`((?:(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+|[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|Dockerfile):\d+(?:-\d+)?)`",
        findings,
    )
    return list(dict.fromkeys(citations))


def score_static_mcp_markdown(markdown: str, golden: Path) -> dict[str, Any]:
    """Measure citation coverage only; a human scorecard owns semantic judgment."""
    citations = _required_golden_citations(golden)
    matched = [citation for citation in citations if citation in markdown]
    return {
        "required_citations": len(citations),
        "matched_citations": len(matched),
        "missing_citations": [citation for citation in citations if citation not in matched],
        "semantic_score_claimed": False,
    }


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


def _static_git_status(repository_root: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["git", "-C", str(repository_root), "status", "--short", "--branch"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": redact(result.stderr),
    }


def _golden_revision(golden: Path) -> str:
    match = re.search(r"^- Revision: `([0-9a-f]{40})`$", golden.read_text(encoding="utf-8"), re.MULTILINE)
    if match is None:
        raise ValueError(f"golden has no pinned revision: {golden}")
    return match.group(1)


def _target_revision(repository_root: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _static_db_records(database: Path) -> list[dict[str, Any]]:
    """Read JSON-bearing OpenCode rows with table and column provenance."""
    if not database.is_file():
        return []
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=1)
        try:
            records: list[dict[str, Any]] = []
            tables = [
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
                if isinstance(row[0], str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", row[0])
            ]
            for table in tables:
                columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
                for row in connection.execute(f'SELECT rowid, * FROM "{table}" ORDER BY rowid'):
                    records.append(
                        {
                            "table": table,
                            "rowid": row[0],
                            "columns": dict(zip(columns, row[1:], strict=True)),
                        }
                    )
            return records
        finally:
            connection.close()
    except sqlite3.Error:
        return []


def _static_json_objects(record: dict[str, Any]) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for value in record.get("columns", {}).values():
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        if not isinstance(value, str):
            continue
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            objects.append(decoded)
    return objects


def _static_message_id(record: dict[str, Any], payload: dict[str, Any]) -> str | None:
    for source in (payload, record.get("columns", {})):
        for key in ("messageID", "messageId", "message_id", "id"):
            value = source.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _static_assistant_markdown(database: Path) -> str:
    """Return text parts that belong to persisted assistant messages only.

    Tool input/output rows are intentionally excluded: a valid final report must
    be authored by the agent rather than reconstructed from MCP results.
    """
    records = _static_db_records(database)
    assistant_ids: set[str] = set()
    for record in records:
        for payload in _static_json_objects(record):
            if payload.get("role") == "assistant":
                identifier = _static_message_id(record, payload)
                if identifier is not None:
                    assistant_ids.add(identifier)

    text_parts: list[str] = []
    for record in records:
        for payload in _static_json_objects(record):
            if payload.get("type") != "text":
                continue
            message_id = _static_message_id(record, payload)
            text = payload.get("text")
            if message_id in assistant_ids and isinstance(text, str):
                text_parts.append(text)
    return "\n".join(text_parts)


STATIC_MCP_PRECISION_TOOLS = ("read_evidence", "locate_evidence", "list_target_paths")

# This is deliberately an observation vocabulary, not a stage controller.  The
# PTY harness only records what OpenCode persisted in its SQLite ``part``
# rows; it does not infer a Skill load from the server's next_skill handoff.
STATIC_MCP_ANALYSIS_TOOLS = (
    "start_analysis",
    *STATIC_MCP_PRECISION_TOOLS,
    *(tool for tool, _status in STATIC_MCP_TOOL_SEQUENCE),
)
_STAGE_BY_SKILL = {
    "analyze-k8s-discovery": "discovery",
    "analyze-k8s-execution": "execution",
    "analyze-k8s-relationships": "relationships",
    "analyze-k8s-boundaries": "boundaries",
    "analyze-k8s-contracts": "contracts",
}


def _static_tool_calls(database: Path) -> list[dict[str, Any]]:
    """Extract named MCP tool parts while preserving their emitted state and row timing.

    Includes the precision-budget and reopen tools (not only the accepted
    `STATIC_MCP_TOOL_SEQUENCE` calls) so `attribute_stage_timeline` can build a
    complete per-turn timeline, not just the sequence-contract-relevant subset.
    """
    expected_tools = set(STATIC_MCP_ANALYSIS_TOOLS)
    calls: list[dict[str, Any]] = []
    for record in _static_db_records(database):
        for payload in _static_json_objects(record):
            name = payload.get("name", payload.get("tool"))
            observed_tool = _tool_name(name)
            if payload.get("type") == "tool" and (observed_tool in expected_tools or name == "skill"):
                call = {"name": name, "state": payload.get("state", payload)}
                columns = record.get("columns", {})
                row_created = columns.get("time_created")
                row_updated = columns.get("time_updated")
                if isinstance(row_created, (int, float)):
                    call["row_time_created"] = row_created
                if isinstance(row_updated, (int, float)):
                    call["row_time_updated"] = row_updated
                for key in ("message_id", "session_id"):
                    value = columns.get(key)
                    if isinstance(value, str) and value:
                        call[key] = value
                calls.append(call)
    unique: list[dict[str, Any]] = []
    for call in calls:
        if call not in unique:
            unique.append(call)
    return unique


def _static_assistant_text_parts(database: Path) -> list[dict[str, Any]]:
    """Extract timestamped assistant text parts without retaining their prose.

    Text is only a liveness signal here.  The final report remains validated
    through ``_static_assistant_markdown``; D09 must not turn trace extraction
    into a second source of report content.
    """
    records = _static_db_records(database)
    assistant_ids: set[str] = set()
    for record in records:
        for payload in _static_json_objects(record):
            if payload.get("role") == "assistant":
                identifier = _static_message_id(record, payload)
                if identifier is not None:
                    assistant_ids.add(identifier)

    parts: list[dict[str, Any]] = []
    for record in records:
        columns = record.get("columns", {})
        for payload in _static_json_objects(record):
            if payload.get("type") != "text" or _static_message_id(record, payload) not in assistant_ids:
                continue
            if not isinstance(payload.get("text"), str) or not payload["text"].strip():
                continue
            part: dict[str, Any] = {"kind": "assistant_text"}
            row_created = columns.get("time_created")
            if isinstance(row_created, (int, float)):
                part["observed_at"] = int(row_created)
            for key in ("message_id", "session_id"):
                value = columns.get(key)
                if isinstance(value, str) and value:
                    part[key] = value
            parts.append(part)
    return parts


def _static_assistant_messages(database: Path) -> list[dict[str, Any]]:
    """Extract persisted assistant message lifecycle fields without prose or errors.

    OpenCode 1.18.14 persists assistant lifecycle in ``message.data`` and
    associates parts through the ``part.message_id`` column.  The extraction
    intentionally retains only safe categorical error information and part
    type presence; report text and raw provider errors remain out of traces.
    """
    records = _static_db_records(database)
    part_types: dict[str, set[str]] = {}
    for record in records:
        columns = record.get("columns", {})
        message_id = columns.get("message_id")
        if not isinstance(message_id, str) or not message_id:
            continue
        for payload in _static_json_objects(record):
            part_type = payload.get("type")
            if isinstance(part_type, str):
                part_types.setdefault(message_id, set()).add(part_type)

    messages: list[dict[str, Any]] = []
    for record in records:
        columns = record.get("columns", {})
        for payload in _static_json_objects(record):
            if payload.get("role") != "assistant":
                continue
            message_id = _static_message_id(record, payload)
            if message_id is None:
                continue
            time_data = payload.get("time") if isinstance(payload.get("time"), dict) else {}
            created = time_data.get("created", columns.get("time_created"))
            completed = time_data.get("completed")
            error = payload.get("error")
            error_category = error.get("name") if isinstance(error, dict) else None
            finish = payload.get("finish")
            if error_category == "MessageAbortedError":
                terminal_state = "aborted"
            elif isinstance(error, dict):
                terminal_state = "errored"
            elif isinstance(completed, (int, float)) or isinstance(finish, str):
                terminal_state = "completed"
            else:
                terminal_state = "active"
            message: dict[str, Any] = {
                "message_id": message_id,
                "terminal_state": terminal_state,
                "part_types": sorted(part_types.get(message_id, set())),
            }
            session_id = columns.get("session_id")
            if isinstance(session_id, str) and session_id:
                message["session_id"] = session_id
            if isinstance(created, (int, float)):
                message["created_at"] = int(created)
            if isinstance(completed, (int, float)):
                message["completed_at"] = int(completed)
            if isinstance(finish, str) and finish:
                message["finish_reason"] = finish
            if isinstance(error_category, str) and error_category:
                message["error_category"] = error_category
            messages.append(message)
    return messages


STAGE_TIMING_ORDER = ("discovery", "execution", "relationships", "boundaries", "contracts")
# Mirrors runtime/python/analysis_pipeline/protocol.py STAGES, kept as an
# independent literal here the same way STATIC_MCP_TOOL_SEQUENCE already is,
# so this measurement code has no import dependency on the trusted server.

_STAGE_ENTRY_TOOL: dict[str, str] = {f"submit_{stage}": stage for stage in STAGE_TIMING_ORDER}
_STAGE_ENTRY_TOOL["start_analysis"] = "dispatcher/start"
_STAGE_ENTRY_TOOL["finalize_analysis"] = "finalize"

_NEXT_STAGE_AFTER: dict[str, str] = {"dispatcher/start": STAGE_TIMING_ORDER[0]}
for _index, _stage in enumerate(STAGE_TIMING_ORDER):
    _NEXT_STAGE_AFTER[_stage] = (
        STAGE_TIMING_ORDER[_index + 1] if _index + 1 < len(STAGE_TIMING_ORDER) else "finalize"
    )


def _tool_call_time_window(call: dict[str, Any]) -> tuple[int | None, int | None]:
    """Best-available (start_ms, end_ms) for one tool call.

    Prefers OpenCode's own `state.time.{start,end}` (present on the NDJSON
    path today; may or may not be populated on the PTY/SQLite path -- an open
    question this ticket's live E2E run resolves). Falls back to the SQLite
    row's `time_created`/`time_updated` columns when `state.time` is absent.
    Returns `(None, None)` rather than a fabricated value when neither source
    is available.
    """
    state = call.get("state")
    if isinstance(state, dict):
        window = state.get("time")
        if isinstance(window, dict):
            start, end = window.get("start"), window.get("end")
            if isinstance(start, (int, float)) and isinstance(end, (int, float)):
                return int(start), int(end)
    row_start = call.get("row_time_created")
    row_end = call.get("row_time_updated")
    if isinstance(row_start, (int, float)) and isinstance(row_end, (int, float)):
        return int(row_start), int(row_end)
    return None, None


def _serialized_size(value: Any) -> int | None:
    """Character-count size of a payload; `None` when there is nothing to measure.

    Never estimates a token count -- character length is the strongest metric
    this harness has without adding a tokenizer dependency the project does
    not already carry.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return len(value)
    try:
        return len(json.dumps(value, ensure_ascii=False))
    except TypeError:
        return None


def _stage_response_status(call: dict[str, Any]) -> str | None:
    """The analysis pipeline's own accepted/rejected/finalized status for one call.

    Deliberately does not reuse `_tool_result_status`: that helper checks
    `state.status` first, which is OpenCode's own tool-execution lifecycle
    field ("completed"/"error") and is present on every call OpenCode
    finished running, successful or domain-rejected alike. It shadows the
    pipeline's real status, which only exists nested inside `state.output`'s
    JSON body -- confirmed against a live `jpetstore-6-summary`/local-sglang
    capture, where every accepted call had `state.status == "completed"`
    (never `"accepted"`) while `json.loads(state.output)["status"]` was the
    real `"accepted"`. Checks both a top-level `status` (the live shape) and
    `structuredContent.status` (the shape `_tool_result_status`'s own test
    coverage assumes) so this reads correctly regardless of which transport
    produced the call.
    """
    state = call.get("state")
    if not isinstance(state, dict):
        return None
    body = state.get("output", state.get("structuredContent"))
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            return None
    if not isinstance(body, dict):
        return None
    status = body.get("status")
    if isinstance(status, str):
        return status
    nested = body.get("structuredContent")
    if isinstance(nested, dict) and isinstance(nested.get("status"), str):
        return nested["status"]
    return None


def _stage_response_payload(call: dict[str, Any]) -> dict[str, Any] | None:
    """Return the server response body for one persisted analysis tool call."""
    state = call.get("state")
    if not isinstance(state, dict):
        return None
    body = state.get("output", state.get("structuredContent"))
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            return None
    if not isinstance(body, dict):
        return None
    structured = body.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    return body


def _liveness_time(event: dict[str, Any], *, handoff: bool = False) -> int | None:
    """Choose a persisted event timestamp without manufacturing one."""
    if event.get("kind") == "assistant_text":
        observed = event.get("observed_at")
        return int(observed) if isinstance(observed, (int, float)) else None
    start, end = _tool_call_time_window(event)
    value = end if handoff else start
    return value if value is not None else None


def _ordered_liveness_events(
    tool_calls: list[dict[str, Any]], assistant_text_parts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Order only timestamped observations; preserve input order for ties/unknowns."""
    combined = [*tool_calls, *assistant_text_parts]
    indexed = list(enumerate(combined))
    return [
        event
        for _index, event in sorted(
            indexed,
            key=lambda item: (
                _liveness_time(item[1]) is None,
                _liveness_time(item[1]) if _liveness_time(item[1]) is not None else item[0],
                item[0],
            ),
        )
    ]


def _liveness_event_detail(event: dict[str, Any]) -> dict[str, Any]:
    if event.get("kind") == "assistant_text":
        return {"kind": "assistant_text", "name": None, "observed_at": _liveness_time(event)}
    name = _tool_name(event.get("name", event.get("tool")))
    if event.get("name") == "skill":
        state = event.get("state") if isinstance(event.get("state"), dict) else {}
        input_value = state.get("input", {})
        skill_name = input_value.get("name") if isinstance(input_value, dict) else None
        return {"kind": "skill", "name": skill_name, "observed_at": _liveness_time(event)}
    return {"kind": "analysis_tool", "name": name, "observed_at": _liveness_time(event)}


def _observation_relation_to_action(
    observations: list[dict[str, Any]], action: dict[str, Any] | None,
) -> str:
    """Return only a timestamp-proven relation to the first stage action.

    This deliberately treats a missing timestamp as unknown, rather than using
    the SQLite row order as a surrogate for temporal order.  A relation cannot
    be expressed when text/Skill observations exist but the stage action does
    not, so that state remains distinct from an absent observation.
    """
    if not observations:
        return "not_observed"
    if action is None:
        return "action_not_observed"
    action_time = _liveness_time(action)
    observation_times = [_liveness_time(observation) for observation in observations]
    if action_time is None or any(value is None for value in observation_times):
        return "order_unknown"
    if all(value <= action_time for value in observation_times):
        return "before"
    if all(value > action_time for value in observation_times):
        return "after"
    return "order_unknown"


def _serialized_byte_size(value: Any) -> int | None:
    """Return a UTF-8 byte size without retaining the observed content."""
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    try:
        return len(
            json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            )
        )
    except (TypeError, ValueError):
        return None


def _event_completion_time(event: dict[str, Any] | None) -> int | None:
    if not isinstance(event, dict):
        return None
    state = event.get("state")
    if not isinstance(state, dict):
        return None
    time_data = state.get("time")
    if not isinstance(time_data, dict):
        return None
    completed = time_data.get("end")
    return int(completed) if isinstance(completed, (int, float)) else None


def _post_skill_turn(
    matching_skill: dict[str, Any] | None,
    first_action: dict[str, Any] | None,
    next_handoff: dict[str, Any] | None,
    assistant_messages: list[dict[str, Any]] | None,
    *,
    terminal_reason: str | None,
) -> dict[str, Any]:
    """Project one causally bounded post-Skill assistant message, if provable.

    The PTY harness observes a message only when its session and creation time
    put it strictly between the expected Skill tool part and the next accepted
    handoff.  When several messages fit without the first action identifying
    one of them, the relation is unavailable rather than guessed.
    """
    unavailable = {"status": "lifecycle_unavailable"}
    if assistant_messages is None or matching_skill is None:
        return unavailable
    skill_time = _liveness_time(matching_skill)
    session_id = matching_skill.get("session_id")
    if skill_time is None or not isinstance(session_id, str) or not session_id:
        return unavailable
    next_handoff_time = _liveness_time(next_handoff) if next_handoff is not None else None
    candidates = [
        message
        for message in assistant_messages
        if message.get("session_id") == session_id
        and isinstance(message.get("created_at"), int)
        and message["created_at"] > skill_time
        and (next_handoff_time is None or message["created_at"] < next_handoff_time)
    ]
    action_message_id = first_action.get("message_id") if isinstance(first_action, dict) else None
    action_candidates = [
        message for message in candidates if message.get("message_id") == action_message_id
    ]
    if len(action_candidates) == 1:
        message = action_candidates[0]
    elif len(candidates) == 1:
        message = candidates[0]
    else:
        return unavailable

    terminal_state = message.get("terminal_state")
    timeout = bool(terminal_reason and "timeout" in terminal_reason.lower())
    if terminal_state == "active" and timeout:
        status = "active_at_timeout"
    elif terminal_state in {"completed", "errored", "aborted"}:
        status = terminal_state
    else:
        # A nonterminal message captured outside a timeout does not establish
        # what the host was doing when the harness ended.
        return unavailable
    part_types = set(message.get("part_types", []))
    return {
        "status": status,
        "message_id": message["message_id"],
        "created_at": message.get("created_at"),
        "completed_at": message.get("completed_at"),
        "finish_reason": message.get("finish_reason"),
        "error_observed": terminal_state in {"errored", "aborted"},
        "error_category": message.get("error_category"),
        "abort_observed": terminal_state == "aborted",
        "part_observations": {
            part_type: "observed" if part_type in part_types else "not_observed"
            for part_type in ("reasoning", "text", "tool", "step-start", "step-finish")
        },
    }


def trace_stage_transitions(
    tool_calls: list[dict[str, Any]],
    assistant_text_parts: list[dict[str, Any]],
    *,
    terminal_reason: str | None,
    assistant_messages: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Characterize accepted handoffs from structured OpenCode artifacts.

    This intentionally observes only persisted Skill tool parts, analysis MCP
    calls, and assistant text parts.  It neither changes the handoff nor
    treats ``next_skill`` itself as proof that OpenCode loaded that Skill.
    """
    events = _ordered_liveness_events(tool_calls, assistant_text_parts)
    skill_events_available = any(event.get("name") == "skill" for event in events)
    transitions: list[dict[str, Any]] = []
    timeout = bool(terminal_reason and "timeout" in terminal_reason.lower())
    handoff_indexes = [
        index
        for index, event in enumerate(events)
        if event.get("kind") != "assistant_text"
        and _tool_name(event.get("name", event.get("tool"))) in _STAGE_ENTRY_TOOL
        and _stage_response_status(event) == "accepted"
        and isinstance(_stage_response_payload(event), dict)
        and isinstance(_stage_response_payload(event).get("next_skill"), str)
    ]

    for handoff_position, index in enumerate(handoff_indexes):
        handoff_call = events[index]
        handoff_tool = _tool_name(handoff_call.get("name", handoff_call.get("tool")))
        payload = _stage_response_payload(handoff_call)
        assert isinstance(payload, dict)
        next_skill = payload.get("next_skill")
        if not isinstance(next_skill, str):
            continue
        host_continuation = payload.get("host_continuation")
        host_owned = (
            isinstance(host_continuation, dict)
            and host_continuation.get("transition_owner") == "host"
            and host_continuation.get("requested_skill") == next_skill
            and host_continuation.get("skill_load") == "completed"
        )
        transition_owner = "host" if host_owned else "model"
        next_stage = _STAGE_BY_SKILL.get(next_skill)
        if next_stage is None:
            # A handoff with an unknown next Skill is observable but cannot be
            # attributed to a stage submission without inventing a mapping.
            next_submission_tool = None
        else:
            next_submission_tool = f"submit_{next_stage}"

        next_handoff_index = (
            handoff_indexes[handoff_position + 1]
            if handoff_position + 1 < len(handoff_indexes)
            else None
        )
        # The next accepted handoff is included as the possible next-stage
        # submission, but no later event can bleed into this transition.
        following = events[index + 1 : next_handoff_index + 1 if next_handoff_index is not None else None]
        next_handoff = events[next_handoff_index] if next_handoff_index is not None else None
        matching_skill = next(
            (
                event
                for event in following
                if event.get("name") == "skill"
                and isinstance(event.get("state"), dict)
                and isinstance(event["state"].get("input"), dict)
                and event["state"]["input"].get("name") == next_skill
            ),
            None,
        )
        analysis_actions = [
            event
            for event in following
            if event.get("kind") != "assistant_text"
            and event.get("name") != "skill"
            and _tool_name(event.get("name", event.get("tool"))) in STATIC_MCP_ANALYSIS_TOOLS
        ]
        first_action = analysis_actions[0] if analysis_actions else None
        first_observable = next(
            (
                event
                for event in following
                if event.get("kind") == "assistant_text"
                or event.get("name") == "skill"
                or _tool_name(event.get("name", event.get("tool"))) in STATIC_MCP_ANALYSIS_TOOLS
            ),
            None,
        )
        submission_calls = [
            event
            for event in following
            if next_submission_tool is not None
            and _tool_name(event.get("name", event.get("tool"))) == next_submission_tool
        ]
        accepted_submission = next(
            (event for event in submission_calls if _stage_response_status(event) == "accepted"),
            None,
        )
        action_time = _liveness_time(first_observable) if first_observable is not None else None
        handoff_time = _liveness_time(handoff_call, handoff=True)
        assistant_text_parts = [
            event for event in following if event.get("kind") == "assistant_text"
        ]
        assistant_text_relation = _observation_relation_to_action(
            assistant_text_parts, first_action
        )
        skill_relation = (
            "before" if host_owned and first_action is not None else (
                "action_not_observed" if host_owned else _observation_relation_to_action(
                    [matching_skill] if matching_skill is not None else [], first_action
                )
            )
        )
        skill_completed_at = handoff_time if host_owned else _event_completion_time(matching_skill)
        first_action_at = _liveness_time(first_action) if first_action is not None else None
        handoff_stage_input = payload.get("stage_input")
        post_skill_turn = (
            {"status": "host_owned_continuation"}
            if host_owned
            else _post_skill_turn(
                matching_skill,
                first_action,
                next_handoff,
                assistant_messages,
                terminal_reason=terminal_reason,
            )
        )
        if accepted_submission is not None:
            classification = "stage_progressed"
        elif first_action is not None:
            classification = "stage_action_observed_no_submission"
        elif host_owned:
            classification = "host_continuation_loaded_no_stage_action"
        elif matching_skill is not None and assistant_messages is not None:
            classification = {
                "active_at_timeout": "model_turn_active_at_timeout",
                "completed": "model_turn_completed_no_stage_action",
                "errored": "model_turn_errored_before_stage_action",
                "aborted": "model_turn_aborted_before_stage_action",
                "lifecycle_unavailable": "post_skill_turn_lifecycle_unavailable",
            }[post_skill_turn["status"]]
        elif assistant_text_parts:
            classification = "assistant_text_no_stage_action"
        elif matching_skill is not None:
            classification = "skill_loaded_no_stage_action"
        elif skill_events_available:
            classification = "next_skill_load_not_observed"
        elif timeout:
            classification = "timeout_before_observable_action"
        else:
            classification = "unobservable_with_current_host_artifacts"

        transitions.append(
            {
                "completed_stage": payload.get("completed_stage"),
                "completed_tool": handoff_tool,
                "next_stage": next_stage,
                "next_skill": next_skill,
                "transition_owner": transition_owner,
                "handoff_observed_at": handoff_time,
                "skill_load": {
                    "status": "completed" if host_owned else ("observed" if matching_skill is not None else ("not_observed" if skill_events_available else "unavailable")),
                    "observed_at": handoff_time if host_owned else (_liveness_time(matching_skill) if matching_skill is not None else None),
                    "completed_at": skill_completed_at,
                    "content_bytes": (
                        _serialized_byte_size(host_continuation.get("skill_content"))
                        if host_owned
                        else _serialized_byte_size(matching_skill.get("state", {}).get("output"))
                        if matching_skill is not None
                        and isinstance(matching_skill.get("state"), dict)
                        and "output" in matching_skill["state"]
                        else None
                    ),
                    "relation_to_first_stage_action": skill_relation,
                },
                "stage_input_serialized_bytes": _serialized_byte_size(handoff_stage_input)
                if isinstance(handoff_stage_input, dict)
                else None,
                "skill_completion_to_first_stage_action_ms": (
                    first_action_at - skill_completed_at
                    if skill_completed_at is not None and first_action_at is not None
                    else None
                ),
                "first_post_handoff_event": _liveness_event_detail(first_observable) if first_observable is not None else None,
                "first_next_stage_action": _liveness_event_detail(first_action) if first_action is not None else None,
                "assistant_text_relation_to_next_stage_action": assistant_text_relation,
                "post_skill_turn": post_skill_turn,
                "next_stage_submission": {
                    "observed": bool(submission_calls),
                    "accepted": accepted_submission is not None,
                    "tool": next_submission_tool,
                    "observed_at": _liveness_time(submission_calls[0]) if submission_calls else None,
                    "accepted_at": _liveness_time(accepted_submission, handoff=True) if accepted_submission is not None else None,
                },
                "gap_to_first_observable_action_ms": (
                    max(0, action_time - handoff_time)
                    if action_time is not None and handoff_time is not None
                    else None
                ),
                "classification": classification,
            }
        )
    return transitions


def attribute_stage_timeline(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build one model-turn record per tool call from `_static_tool_calls` output.

    Stage attribution: a `submit_<stage>` / `start_analysis` / `finalize_analysis`
    call is attributed to the stage its own name names. Every other tool
    (`read_evidence`, `locate_evidence`, `list_target_paths`)
    inherits whichever stage was most recently *entered* by an accepted
    stage-entering call -- "entered" meaning the stage that call's accepted
    response hands control to next, not the stage it just completed -- and
    defaults to `unknown` before the first such call. A rejected/errored
    stage-entering call does not advance this pointer.

    Timing ("model-turn latency"): `elapsed_ms` is the harness-observed
    wall-clock gap between the previous tool call's end and this call's
    start -- the interval OpenCode spent orchestrating/waiting on the model
    before issuing this call -- not isolated neural-network inference time.
    A tool call's own execution time lives separately under
    `tool_calls[0]["elapsed_ms"]`. Either is `None`, never a fabricated
    number, when no timestamp source is available; a negative gap (clock
    skew between sources) clamps to `0` rather than raising, since this is
    measurement code observing an external process.
    """
    turns: list[dict[str, Any]] = []
    current_stage = "unknown"
    previous_end: int | None = None
    previous_output: Any = None
    for call in tool_calls:
        name = _tool_name(call.get("name", call.get("tool"))) or "unknown"
        entered_stage = _STAGE_ENTRY_TOOL.get(name)
        stage = entered_stage if entered_stage is not None else current_stage
        start, end = _tool_call_time_window(call)
        elapsed_ms = None if start is None or previous_end is None else max(0, start - previous_end)
        tool_elapsed_ms = None if start is None or end is None else max(0, end - start)
        state = call.get("state") if isinstance(call.get("state"), dict) else {}
        turns.append(
            {
                "stage": stage,
                "started_at": previous_end,
                "completed_at": start,
                "elapsed_ms": elapsed_ms,
                "tool_calls": [{"tool": name, "elapsed_ms": tool_elapsed_ms}],
                "input_chars": _serialized_size(previous_output),
                "output_chars": _serialized_size(state.get("input")),
            }
        )
        if entered_stage is not None and _stage_response_status(call) in {"accepted", "finalized"}:
            current_stage = _NEXT_STAGE_AFTER.get(entered_stage, entered_stage)
        if end is not None:
            previous_end = end
        previous_output = state.get("output", state.get("structuredContent"))
    return turns


def summarize_stage_timeline(turns: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Reduce `attribute_stage_timeline` output to per-stage totals for one attempt.

    A stage with no timestamp coverage at all reports `None` sums/means, not
    `0` -- an untimed stage must not look like a fast one.
    """
    model_ms_by_stage: dict[str, list[int]] = {}
    tool_ms_by_stage: dict[str, list[int]] = {}
    turn_counts: dict[str, int] = {}
    for turn in turns:
        stage = turn.get("stage", "unknown")
        turn_counts[stage] = turn_counts.get(stage, 0) + 1
        if turn.get("elapsed_ms") is not None:
            model_ms_by_stage.setdefault(stage, []).append(turn["elapsed_ms"])
        for tool_call in turn.get("tool_calls", []):
            if tool_call.get("elapsed_ms") is not None:
                tool_ms_by_stage.setdefault(stage, []).append(tool_call["elapsed_ms"])

    summary: dict[str, dict[str, Any]] = {}
    for stage, turn_count in turn_counts.items():
        model_values = model_ms_by_stage.get(stage, [])
        tool_values = tool_ms_by_stage.get(stage, [])
        summary[stage] = {
            "turn_count": turn_count,
            "model_turn_ms_total": sum(model_values) if model_values else None,
            "model_turn_ms_mean": (sum(model_values) / len(model_values)) if model_values else None,
            "model_turn_ms_max": max(model_values) if model_values else None,
            "tool_ms_total": sum(tool_values) if tool_values else None,
            "tool_ms_mean": (sum(tool_values) / len(tool_values)) if tool_values else None,
        }
    return summary


def static_mcp_runtime_environment(
    base: dict[str, str],
    *,
    home: Path,
    config: Path,
    config_dir: Path,
    log_root: Path,
    transition_mode: str = "model_routed",
) -> dict[str, str]:
    """Create an isolated Windows-native PTY environment.

    Only OS launch prerequisites and the explicit provider credential are
    inherited. User profile directories are redirected into the temporary
    acceptance home so global OpenCode state cannot influence a result.
    """
    allowed = (
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "ComSpec",
        "LANG",
        "LC_ALL",
        "TERM",
        "COLORTERM",
        "NO_COLOR",
        "UPSTAGE_API_KEY",
    )
    environment = {key: base[key] for key in allowed if base.get(key)}
    environment.setdefault("TERM", "xterm-256color")
    environment.setdefault("COLORTERM", "truecolor")
    private_tmp = home / "tmp"
    environment.update(
        {
            "HOME": str(home.resolve()),
            "USERPROFILE": str(home.resolve()),
            "APPDATA": str((home / "AppData" / "Roaming").resolve()),
            "LOCALAPPDATA": str((home / "AppData" / "Local").resolve()),
            "OPENCODE_CONFIG": str(config.resolve()),
            "OPENCODE_CONFIG_DIR": str(config_dir.resolve()),
            "XDG_CONFIG_HOME": str((home / ".config").resolve()),
            "XDG_DATA_HOME": str((home / ".local" / "share").resolve()),
            "XDG_STATE_HOME": str((home / ".local" / "state").resolve()),
            "XDG_CACHE_HOME": str((home / ".cache").resolve()),
            "TEMP": str(private_tmp.resolve()),
            "TMP": str(private_tmp.resolve()),
            "OPENCODE_DISABLE_AUTOUPDATE": "1",
            "OPENCODE_TRACE_LOG_ROOT": str(log_root.resolve()),
            "ANALYSIS_TRANSITION_MODE": transition_mode,
            "ANALYSIS_PIPELINE_SKILL_ROOT": str((config_dir / "skills").resolve()),
            "PYWINPTY_BLOCK": "0",
        }
    )
    return environment


def windows_pty_process(package_root: Path | None) -> Any:
    """Load the test-only Windows PTY dependency without making it runtime code."""
    if os.name != "nt":
        raise ValueError("static MCP acceptance requires a Windows PTY")
    if package_root is not None:
        resolved = package_root.resolve()
        if not resolved.is_dir():
            raise ValueError(f"Windows PTY package directory does not exist: {resolved}")
        sys.path.insert(0, str(resolved))
    try:
        from winpty import PtyProcess
    except ImportError as error:
        raise ValueError(
            "Windows PTY support is unavailable; install pywinpty for this test or pass --windows-pty-root"
        ) from error
    return PtyProcess


def spawn_windows_pty(
    pty_process: Any,
    launch: list[str],
    *,
    cwd: str,
    environment: dict[str, str],
) -> Any:
    """Spawn with nonblocking reads in the harness process, not only its child."""
    previous = os.environ.get("PYWINPTY_BLOCK")
    os.environ["PYWINPTY_BLOCK"] = "0"
    try:
        return pty_process.spawn(launch, cwd=cwd, env=environment, dimensions=(50, 180))
    finally:
        if previous is None:
            os.environ.pop("PYWINPTY_BLOCK", None)
        else:
            os.environ["PYWINPTY_BLOCK"] = previous


def read_windows_pty(pty: Any) -> str:
    """Read a bounded terminal chunk while dropping pywinpty's idle sentinel."""
    try:
        return pty.read(65536).replace("0011Ignore", "")
    except EOFError:
        return ""


def _static_opencode_databases(home: Path) -> list[Path]:
    """Discover OpenCode databases beneath the per-case isolated profile only."""
    return sorted(path for path in home.rglob("opencode.db") if path.is_file())


def _static_assistant_markdown_from_home(home: Path) -> str:
    return "\n".join(_static_assistant_markdown(database) for database in _static_opencode_databases(home))


def static_mcp_terminal_stop_reason(terminal: str) -> str | None:
    """Recognize an idle OpenCode agent before the PTY timeout elapses."""
    marker = "No further tool calls can be made until the next user interaction or handoff acceptance."
    if marker in terminal:
        return "OpenCode agent stopped before the MCP workflow finalized"
    return None


def _run_static_mcp_case(
    case: dict[str, Any],
    golden: dict[str, Any],
    *,
    source_config: Path,
    output_dir: Path,
    opencode: str,
    model: str | None,
    timeout: float,
    runtime_python: str,
    pty_process: Any,
    transition_mode: str = "model_routed",
) -> dict[str, Any]:
    """Run one fresh user command in a Windows-native PTY and preserve evidence."""
    command_directory = Path(case["command_directory"]).resolve()
    selected = case["target_path"]
    target = (Path(selected) if case["path_style"] == "absolute" else command_directory / selected).resolve()
    case_dir = output_dir / case["id"]
    case_dir.mkdir(parents=True, exist_ok=True)
    before = _static_git_status(target)
    golden_path = ROOT / "tests" / "evaluation" / golden["golden"]
    expected_revision = _golden_revision(golden_path)
    actual_revision = _target_revision(target)
    trace: dict[str, Any] = {
        "case_id": case["id"],
        "mode": case["mode"],
        "target": str(target),
        "target_status_before": before,
        "golden": golden["golden"],
        "golden_sha256": golden["sha256"],
        "expected_revision": expected_revision,
        "actual_revision": actual_revision,
        "transition_mode": transition_mode,
        "status": "FAIL",
    }
    if before["returncode"]:
        trace["reason"] = "target Git status could not be read"
        return trace
    if actual_revision != expected_revision:
        trace["reason"] = "target revision does not match its sealed golden"
        return trace

    with tempfile.TemporaryDirectory(prefix="opencode-acceptance-") as temporary:
        temporary_root = Path(temporary)
        bundle = copy_bundle(ROOT, temporary_root / "bundle")
        config_dir = temporary_root / "config"
        install_bundle(bundle, config_dir)
        config_path = temporary_root / "opencode.json"
        isolated_config_bundle(
            source_config,
            config_path,
            config_dir,
            runtime_python=runtime_python,
        )
        home = temporary_root / "home"
        for directory in (
            home,
            home / "tmp",
            home / "AppData" / "Roaming",
            home / "AppData" / "Local",
            case_dir / "logs",
        ):
            directory.mkdir(parents=True, exist_ok=True)
        environment = static_mcp_runtime_environment(
            os.environ,
            home=home,
            config=config_path,
            config_dir=config_dir,
            log_root=case_dir / "logs",
            transition_mode=transition_mode,
        )
        launch = [opencode, str(command_directory), "--mini", "--agent", AGENT_ID]
        if model:
            launch.extend(["--model", model])
        terminal = ""
        pty: Any | None = None
        attempt_started = time.monotonic()
        try:
            pty = spawn_windows_pty(pty_process, launch, cwd=str(command_directory), environment=environment)
            ready_deadline = time.monotonic() + min(30, timeout)
            while time.monotonic() < ready_deadline:
                terminal = (terminal + read_windows_pty(pty))[-1_000_000:]
                if "Ask anything" in terminal:
                    break
                time.sleep(0.1)
            else:
                trace["reason"] = "OpenCode Windows PTY did not reach the input-ready state"
                return trace
            command_prefix, command_body, submit = static_mcp_command_keystrokes(case)
            pty.write(command_prefix)
            catalog_deadline = time.monotonic() + min(4, timeout)
            while time.monotonic() < catalog_deadline:
                terminal = (terminal + read_windows_pty(pty))[-1_000_000:]
                time.sleep(0.1)
            pty.write(command_body)
            time.sleep(0.25)
            terminal = (terminal + read_windows_pty(pty))[-1_000_000:]
            pty.write(submit)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                terminal = (terminal + read_windows_pty(pty))[-1_000_000:]
                stopped = static_mcp_terminal_stop_reason(terminal)
                if stopped is not None:
                    trace["reason"] = stopped
                    return trace
                database_text = _static_assistant_markdown_from_home(home)
                try:
                    extract_markdown_report(database_text, mode=case["mode"])
                    break
                except ValueError:
                    time.sleep(0.25)
            else:
                trace["reason"] = "OpenCode PTY did not produce a complete final Markdown report before timeout"
                return trace

            report = retain_agent_markdown(database_text, case_dir, target, mode=case["mode"])
            tool_calls = [
                call
                for database in _static_opencode_databases(home)
                for call in _static_tool_calls(database)
            ]
            transition_errors = static_mcp_transition_errors(tool_calls)
            after = _static_git_status(target)
            score = score_static_mcp_markdown(report, golden_path)
            trace.update(
                {
                    "status": "PASS" if not transition_errors and before == after else "FAIL",
                    "target_status_after": after,
                    "target_unchanged": before == after,
                    "tool_calls": tool_calls,
                    "turns": attribute_stage_timeline(tool_calls),
                    "transition_errors": transition_errors,
                    "score": score,
                    "report_file": str((case_dir / "report.md").resolve()),
                }
            )
            if trace["status"] == "FAIL":
                trace["reason"] = "; ".join(transition_errors) or "target repository changed"
            return trace
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            trace["reason"] = redact(str(error))
            trace["target_status_after"] = _static_git_status(target)
            return trace
        finally:
            if pty is not None and pty.isalive():
                try:
                    pty.terminate(force=True)
                except OSError:
                    pass
            if terminal:
                (case_dir / "terminal.log").write_text(redact(terminal), encoding="utf-8")
            trace.setdefault("terminal_file", str((case_dir / "terminal.log").resolve()))
            trace.setdefault("total_elapsed_ms", int((time.monotonic() - attempt_started) * 1000))
            # Timeout and early-stop paths return before the success-path
            # integrity audit.  Preserve the same before/after target evidence
            # for incomplete liveness traces without treating it as success.
            after = _static_git_status(target)
            trace.setdefault("target_status_after", after)
            trace.setdefault("target_unchanged", before == after)
            if "turns" not in trace:
                # A timeout/stopped/ready-deadline exit returned before the
                # success path computed tool_calls; salvage whatever the
                # database holds so a partial run is still measurable instead
                # of leaving the attempt with no timing evidence at all.
                salvaged_calls = [
                    call
                    for database in _static_opencode_databases(home)
                    for call in _static_tool_calls(database)
                ]
                trace["tool_calls"] = salvaged_calls
                trace["turns"] = attribute_stage_timeline(salvaged_calls)
            databases = _static_opencode_databases(home)
            assistant_text_parts = [
                part
                for database in databases
                for part in _static_assistant_text_parts(database)
            ]
            assistant_messages = [
                message
                for database in databases
                for message in _static_assistant_messages(database)
            ]
            trace["stage_transitions"] = trace_stage_transitions(
                trace.get("tool_calls", []),
                assistant_text_parts,
                terminal_reason=trace.get("reason"),
                assistant_messages=assistant_messages,
            )
            trace["stage_transition_observability"] = {
                "skill_load": (
                    "available"
                    if any(call.get("name") == "skill" for call in trace.get("tool_calls", []))
                    else "unavailable"
                ),
                "assistant_text": "available" if assistant_text_parts else "unavailable",
                "post_skill_turn_lifecycle": (
                    "available" if assistant_messages else "unavailable"
                ),
            }
            (case_dir / "trace.json").write_text(
                json.dumps(redact(trace), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )


def _run_static_mcp_acceptance(args: argparse.Namespace, cases_path: Path) -> int:
    golden_manifest_path = ROOT / "tests" / "evaluation" / "static-mcp-golden-manifest.json"
    sealed = load_static_mcp_golden_manifest(golden_manifest_path)
    cases = load_static_mcp_cases(cases_path)
    errors = validate_static_mcp_cases(cases, sealed)
    if errors:
        raise ValueError("static MCP case manifest is invalid: " + "; ".join(errors))
    selected = set(args.case_ids or [])
    if selected:
        unknown = selected - {case["id"] for case in cases}
        if unknown:
            raise ValueError("unknown static MCP case ID: " + ", ".join(sorted(unknown)))
        cases = [case for case in cases if case["id"] in selected]
    if not args.interactive:
        raise ValueError("static MCP acceptance requires --interactive for every case")
    runtime_python = args.runtime_python or sys.executable
    pty_process = windows_pty_process(args.windows_pty_root)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    results = [
        _run_static_mcp_case(
            case,
            sealed[case["id"]],
            source_config=args.config.resolve(),
            output_dir=output_dir,
            opencode=args.opencode,
            model=args.model,
            timeout=args.timeout,
            runtime_python=runtime_python,
            pty_process=pty_process,
            transition_mode=args.transition_mode,
        )
        for case in cases
    ]
    (output_dir / "static-mcp-results.json").write_text(
        json.dumps(redact({"cases": results}), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for result in results:
        print(f"static-mcp/{result['case_id']}: {result['status']}" + (f" ({result['reason']})" if result.get("reason") else ""))
    return 0 if all(result["status"] == "PASS" for result in results) else 1


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
    parser.add_argument("--runtime-python", help=argparse.SUPPRESS)
    parser.add_argument(
        "--windows-pty-root",
        type=Path,
        help="Windows interactive E2E에만 사용하는 pywinpty 설치 경로입니다.",
    )
    parser.add_argument(
        "--transition-mode",
        choices=("model_routed", "host_owned"),
        default="model_routed",
        help="D12 전환 소유권 실험 모드입니다. 기본값은 기존 model_routed입니다.",
    )
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    payload = load_json(args.cases)
    if isinstance(payload, dict) and payload.get("suite") == "static-mcp-opencode":
        if args.mode != "isolated":
            parser.error("static MCP acceptance requires --mode isolated")
        if args.config is None:
            parser.error("static MCP acceptance requires --config")
        return _run_static_mcp_acceptance(args, args.cases.resolve())
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
            agent_path = config_dir / "agents" / f"{AGENT_ID}.md"
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
