#!/usr/bin/env python3
"""Build the static multi-Skill distribution bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

try:
    from scripts.validate_skill import validate_bundle
except ModuleNotFoundError:  # Direct invocation: python3 scripts/build_dist.py ...
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
STAGE_IDS = tuple(skill.removeprefix("analyze-k8s-") for skill in SKILL_IDS[1:] if skill != "analyze-k8s-finalize")
SKILL_POLICIES = {
    "analyze-repo-for-kubernetes": {"tools": ["start_analysis"], "references": []},
    "analyze-k8s-discovery": {
        "tools": ["list_target_paths", "read_evidence", "locate_evidence", "get_target_git_metadata", "submit_discovery"],
        "references": ["references/workflow.md", "references/language-discovery-rules.md", "references/payload-contract.json"],
    },
    **{
        f"analyze-k8s-{stage}": {"tools": [], "references": ["references/payload-contract.json"]}
        for stage in STAGE_IDS if stage != "discovery"
    },
    "analyze-k8s-finalize": {"tools": [], "references": []},
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def revision(root: Path) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False)
    return result.stdout.strip() or "unknown"


def project_contracts(root: Path, skills: Path) -> None:
    source = json.loads((root / "contracts" / "stage-payload-contracts.json").read_text(encoding="utf-8"))
    for stage in STAGE_IDS:
        path = skills / f"analyze-k8s-{stage}" / "references" / "payload-contract.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(source["stages"][stage], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def declared_runtime_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for line in (root / "runtime-files.txt").read_text(encoding="utf-8").splitlines():
        relative = line.strip()
        if not relative or relative.startswith("#"):
            continue
        source = root / relative
        if not source.is_file():
            raise ValueError(f"declared runtime file is missing: {relative}")
        paths.append(Path(relative))
    return paths


def bundle_destination(staging: Path, relative: Path) -> Path:
    parts = relative.parts
    if relative == Path("SKILL.md"):
        return staging / "skills" / SKILL_IDS[0] / "SKILL.md"
    if parts[:2] == ("runtime", "stage-skills"):
        return staging / "skills" / parts[2] / Path(*parts[3:])
    if parts[:2] == ("runtime", "python"):
        return staging / "runtime" / "python" / Path(*parts[2:])
    if parts[:2] == ("runtime", "agents"):
        return staging / "agents" / Path(*parts[2:])
    if parts[:2] == ("runtime", "commands"):
        return staging / "commands" / Path(*parts[2:])
    if parts[0] in {"assets", "contracts"}:
        return staging / relative
    raise ValueError(f"runtime file has no bundle destination: {relative.as_posix()}")


def build(source_root: Path, output: Path) -> Path:
    source_root = source_root.resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".skill-bundle-", dir=output.parent))
    staging = temporary / output.name
    try:
        for relative in declared_runtime_files(source_root):
            destination = bundle_destination(staging, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_root / relative, destination)
        project_contracts(source_root, staging / "skills")
        shutil.copyfile(source_root / "contracts" / "skill-bundle-manifest.schema.json", staging / "skill-bundle-manifest.schema.json")
        files = {path.relative_to(staging).as_posix(): {"sha256": sha256(path), "size": path.stat().st_size} for path in sorted(staging.rglob("*")) if path.is_file()}
        (staging / "bundle-manifest.json").write_text(json.dumps({"source_revision": revision(source_root), "skills": list(SKILL_IDS), "skill_policies": SKILL_POLICIES, "files": files}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        errors = validate_bundle(staging)
        if errors:
            raise ValueError("invalid bundle: " + "; ".join(errors))
        backup = temporary / f".{output.name}.backup"
        if output.exists() or output.is_symlink():
            os.replace(output, backup)
        try:
            os.replace(staging, output)
        except Exception:
            if backup.exists() or backup.is_symlink():
                os.replace(backup, output)
            raise
        else:
            if backup.exists() or backup.is_symlink():
                if backup.is_dir() and not backup.is_symlink():
                    shutil.rmtree(backup)
                else:
                    backup.unlink()
        return output
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "dist" / "bundle")
    args = parser.parse_args()
    build(args.source_root, args.output)
    print(f"Built bundle: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
