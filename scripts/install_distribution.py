#!/usr/bin/env python3
"""Install one validated distribution to multiple paths without partial success."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import uuid


def remove(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def install(source: Path, targets: list[Path], fail_after: int | None = None) -> None:
    source = source.resolve()
    stages: list[tuple[Path, Path]] = []
    committed: list[tuple[Path, Path | None]] = []
    try:
        for target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            stage = target.parent / f".{target.name}.stage-{uuid.uuid4().hex}"
            shutil.copytree(source, stage)
            stages.append((target, stage))

        for index, (target, stage) in enumerate(stages, start=1):
            backup = target.parent / f".{target.name}.backup-{uuid.uuid4().hex}" if (target.exists() or target.is_symlink()) else None
            if backup is not None:
                target.replace(backup)
            stage.replace(target)
            committed.append((target, backup))
            if fail_after == index:
                raise RuntimeError(f"injected failure after commit {index}")
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Install a distribution atomically across paths.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, action="append", required=True)
    args = parser.parse_args()
    install(args.source, args.target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
