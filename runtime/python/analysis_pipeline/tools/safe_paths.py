"""Fail-closed path handling for untrusted analysis targets."""
from __future__ import annotations

from pathlib import Path


def _is_reparse_or_link(path: Path) -> bool:
    stat = path.lstat()
    attributes = getattr(stat, "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & 0x400)


def _within(root: Path, candidate: Path) -> Path | None:
    try:
        return candidate.relative_to(root)
    except ValueError:
        return None


def safe_path(worktree, value, trusted_roots=()):
    root = Path(worktree).resolve()
    supplied = Path(value)
    if not supplied.is_absolute() and ".." in supplied.parts:
        raise ValueError("path is outside the target or trusted Skill")
    candidate = supplied if supplied.is_absolute() else root / supplied
    candidate = candidate.absolute()
    allowed_roots = [root, *[Path(item).resolve() for item in trusted_roots]]
    selected_root = next((allowed for allowed in allowed_roots if _within(allowed, candidate) is not None), None)
    if selected_root is None:
        raise ValueError("path is outside the target or trusted Skill")
    relative = _within(selected_root, candidate)
    if relative is None or _is_reparse_or_link(selected_root):
        raise ValueError("path is symlink or reparse point")
    current = selected_root
    for component in relative.parts:
        current = current / component
        if _is_reparse_or_link(current):
            raise ValueError("path is symlink or reparse point")
    return candidate
