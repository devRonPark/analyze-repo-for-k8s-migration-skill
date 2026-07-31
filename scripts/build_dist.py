#!/usr/bin/env python3
"""Build the minimal OpenCode Skill distribution from an explicit allowlist."""
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
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.validate_skill import validate
from scripts.project_metadata import load


def read_allowlist(source_root: Path) -> list[str]:
    allowlist_path = source_root / "runtime-files.txt"
    entries = [
        line.strip()
        for line in allowlist_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if len(entries) != len(set(entries)):
        raise ValueError("runtime-files.txt contains duplicate entries")
    for entry in entries:
        path = Path(entry)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"runtime allowlist path must be relative: {entry}")
        if not (source_root / path).is_file():
            raise ValueError(f"runtime allowlist file is missing: {entry}")
    if "SKILL.md" not in entries:
        raise ValueError("runtime allowlist must include SKILL.md")
    return entries


def source_revision(source_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=source_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def replace_output(staging: Path, output: Path) -> None:
    """Replace output while retaining a recoverable previous directory."""
    backup = output.parent / f".{output.name}.backup-{uuid.uuid4().hex}"
    had_output = output.exists() or output.is_symlink()
    if had_output:
        os.replace(output, backup)
    try:
        os.replace(staging, output)
    except OSError:
        if had_output:
            os.replace(backup, output)
        raise
    if had_output:
        if backup.is_dir() and not backup.is_symlink():
            shutil.rmtree(backup)
        else:
            backup.unlink()


def build(source_root: Path, output: Path) -> Path:
    source_root = source_root.resolve()
    output = output.resolve()
    metadata = load(source_root)
    entries = read_allowlist(source_root)
    output.parent.mkdir(parents=True, exist_ok=True)

    temporary_root = Path(tempfile.mkdtemp(prefix=".skill-build-", dir=output.parent))
    staging = temporary_root / metadata.skill_id
    try:
        for entry in entries:
            destination = staging / entry
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_root / entry, destination)

        manifest = {
            "skill_id": metadata.skill_id,
            "version": metadata.skill_version,
            "source_revision": source_revision(source_root),
            "files": {},
        }
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                relative = path.relative_to(staging).as_posix()
                manifest["files"][relative] = {
                    "sha256": sha256(path),
                    "size": path.stat().st_size,
                }
        (staging / metadata.manifest_name).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        errors = validate(staging)
        if errors:
            raise ValueError("built distribution failed validation: " + "; ".join(errors))

        replace_output(staging, output)
        return output
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenCode Skill runtime distribution을 생성합니다.")
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="생성할 distribution 디렉터리 (기본값: dist/analyze-repo-for-kubernetes)",
    )
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    try:
        metadata = load(source_root)
        output = args.output or source_root / "dist" / metadata.skill_id
        destination = build(source_root, output)
    except (OSError, ValueError) as error:
        print(f"실패: {error}")
        return 1
    print(f"성공: OpenCode Skill distribution을 생성했습니다: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
