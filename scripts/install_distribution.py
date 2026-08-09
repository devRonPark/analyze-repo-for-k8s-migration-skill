#!/usr/bin/env python3
"""Install one validated distribution to multiple paths without partial success."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

try:
    from scripts.validate_skill import validate_bundle
except ModuleNotFoundError:  # Direct invocation: python3 scripts/install_distribution.py ...
    from validate_skill import validate_bundle


SKILL_IDS = (
    "analyze-repo-for-kubernetes",
    "analyze-k8s-discovery",
    "analyze-k8s-execution",
    "analyze-k8s-relationships",
    "analyze-k8s-boundaries",
    "analyze-k8s-contracts",
    "analyze-k8s-finalize",
)
PROJECT_ID = "analyze-repo-for-kubernetes"
AGENT_NAME = "kubernetes-migration-analyzer.md"
COMMAND_NAME = "analyze-repo-for-kubernetes.md"


def remove(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def copy_entry(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)


def install_entries(entries: list[tuple[Path, Path]]) -> None:
    """Replace related files and directories as one rollback unit."""
    stages: list[tuple[Path, Path]] = []
    committed: list[tuple[Path, Path | None]] = []
    try:
        for source, target in entries:
            target.parent.mkdir(parents=True, exist_ok=True)
            stage = target.parent / f".{target.name}.new-{uuid.uuid4().hex[:8]}"
            copy_entry(source, stage)
            stages.append((target, stage))

        for target, stage in stages:
            backup = target.parent / f".{target.name}.old-{uuid.uuid4().hex[:8]}" if (target.exists() or target.is_symlink()) else None
            if backup is not None:
                target.replace(backup)
            committed.append((target, backup))
            stage.replace(target)
    except Exception:
        for target, backup in reversed(committed):
            remove(target)
            if backup is not None and (backup.exists() or backup.is_symlink()):
                backup.replace(target)
        raise
    else:
        for _, backup in committed:
            if backup is not None:
                remove(backup)
    finally:
        for _, stage in stages:
            remove(stage)


def install(source: Path, targets: list[Path]) -> None:
    source = source.resolve()
    install_entries([(source, target) for target in targets])


def render_opencode_mcp_fragment(runtime_root: Path) -> dict[str, object]:
    """Create the portable MCP fragment for an already-installed runtime."""
    launcher = (runtime_root / "python" / "launch_mcp.py").resolve()
    return {
        "mcp": {
            "analysis": {
                "type": "local",
                "command": [sys.executable, str(launcher)],
                "enabled": True,
            }
        }
    }


def _load_manifest(source_bundle: Path) -> dict[str, object]:
    manifest_path = source_bundle / "bundle-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"bundle manifest is missing: {manifest_path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"bundle manifest is invalid: {manifest_path}") from error
    if not isinstance(manifest, dict) or manifest.get("skills") != list(SKILL_IDS):
        raise ValueError("bundle manifest does not declare the required static Skill inventory")
    return manifest


def _require_bundle_layout(source_bundle: Path) -> None:
    skills = source_bundle / "skills"
    observed_skills = {path.name for path in skills.iterdir() if path.is_dir()} if skills.is_dir() else set()
    if observed_skills != set(SKILL_IDS):
        raise ValueError("bundle Skill inventory contains missing or orphaned members")
    required = (
        source_bundle / "runtime" / "python" / "launch_mcp.py",
        source_bundle / "contracts" / "stage-payload-contracts.json",
        source_bundle / "assets",
        source_bundle / "agents" / AGENT_NAME,
        source_bundle / "commands" / COMMAND_NAME,
    )
    missing = [str(path.relative_to(source_bundle)) for path in required if not path.exists()]
    if missing:
        raise ValueError(f"bundle is missing required members: {', '.join(missing)}")


def bundle_targets(source_bundle: Path, config_root: Path) -> list[Path]:
    """Return every OpenCode-owned destination in deterministic order."""
    source_bundle = source_bundle.resolve()
    config_root = config_root.resolve()
    skill_targets = [config_root / "skills" / skill_id for skill_id in SKILL_IDS]
    project_root = config_root / PROJECT_ID
    return [
        *skill_targets,
        project_root / "runtime",
        project_root / "contracts",
        project_root / "assets",
        config_root / "agent" / AGENT_NAME,
        config_root / "command" / COMMAND_NAME,
        project_root / "opencode-mcp.json",
    ]


def install_bundle(source_bundle: Path, config_root: Path) -> None:
    """Install one validated seven-Skill bundle with all-or-nothing rollback."""
    source_bundle = source_bundle.resolve()
    config_root = config_root.resolve()
    errors = validate_bundle(source_bundle)
    if errors:
        raise ValueError("invalid bundle: " + "; ".join(errors))
    _load_manifest(source_bundle)
    _require_bundle_layout(source_bundle)
    project_root = config_root / PROJECT_ID
    fragment_source: Path | None = None
    try:
        runtime_source = source_bundle / "runtime"
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".opencode-mcp.json",
            delete=False,
        ) as stream:
            fragment_source = Path(stream.name)
            stream.write(
                json.dumps(render_opencode_mcp_fragment(project_root / "runtime"), ensure_ascii=False, indent=2) + "\n",
            )
        entries = [
            *((source_bundle / "skills" / skill_id, config_root / "skills" / skill_id) for skill_id in SKILL_IDS),
            (runtime_source, project_root / "runtime"),
            (source_bundle / "contracts", project_root / "contracts"),
            (source_bundle / "assets", project_root / "assets"),
            (source_bundle / "agents" / AGENT_NAME, config_root / "agent" / AGENT_NAME),
            (source_bundle / "commands" / COMMAND_NAME, config_root / "command" / COMMAND_NAME),
            (fragment_source, project_root / "opencode-mcp.json"),
        ]
        install_entries(entries)
    finally:
        if fragment_source is not None:
            remove(fragment_source)


def main() -> int:
    parser = argparse.ArgumentParser(description="Install a distribution atomically across paths.")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--target", type=Path, action="append")
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--config-root", type=Path)
    args = parser.parse_args()
    if args.bundle is not None or args.config_root is not None:
        if args.bundle is None or args.config_root is None or args.source is not None or args.target:
            parser.error("--bundle and --config-root must be used together without --source or --target")
        install_bundle(args.bundle, args.config_root)
        return 0
    if args.source is None or not args.target:
        parser.error("--source and at least one --target are required")
    install(args.source, args.target)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
