"""Isolate Python test temp fixtures from managed Windows temp ACLs."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from uuid import uuid4


_TEMP_ROOT: Path | None = None
_TEMP_BASE: Path | None = None
_REPO_ROOT: Path | None = None
_NAMESPACE: str | None = None
_PREVIOUS_TEMP_DIR = tempfile.tempdir
_PREVIOUS_TEMPORARY_DIRECTORY = tempfile.TemporaryDirectory
_PREVIOUS_MKDTEMP = tempfile.mkdtemp
_PREVIOUS_TEMP = os.environ.get("TEMP")
_PREVIOUS_TMP = os.environ.get("TMP")
_CLEANUP_FAILURES: list[str] = []
_OWNER_MARKER = ".codex-test-owner.json"


def _namespace(repo_root: Path) -> str:
    return hashlib.sha256(str(repo_root).casefold().encode("utf-8")).hexdigest()[:16]


def _is_reparse_or_link(path: Path) -> bool:
    junction_checker = getattr(os, "isjunction", None)
    return path.is_symlink() or bool(junction_checker and junction_checker(path))


def _contained(path: Path, base: Path) -> bool:
    try:
        return path.resolve(strict=False).is_relative_to(base.resolve(strict=True))
    except (OSError, RuntimeError):
        return False


def _pid_is_alive(pid: int) -> bool:
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _read_owner(root: Path) -> dict[str, object] | None:
    marker = root / _OWNER_MARKER
    if _is_reparse_or_link(root) or _is_reparse_or_link(marker) or not marker.is_file():
        return None
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _remove_owned_root(root: Path, *, fail_fast: bool) -> bool:
    base = _TEMP_BASE
    namespace = _NAMESPACE
    repo_root = _REPO_ROOT
    if base is None or namespace is None or repo_root is None:
        return False
    if not root.is_dir() or _is_reparse_or_link(root) or not _contained(root, base):
        return False
    owner = _read_owner(root)
    if owner is None:
        return False
    if owner.get("namespace") != namespace or owner.get("repo_root") != str(repo_root):
        return False
    pid = owner.get("pid")
    if isinstance(pid, int) and pid != os.getpid() and _pid_is_alive(pid):
        return False
    try:
        _PREVIOUS_TEMPORARY_DIRECTORY._rmtree(str(root), ignore_errors=False)
    except OSError as error:
        message = f"temporary root cleanup failed: {root}: {type(error).__name__}: {error}"
        _CLEANUP_FAILURES.append(message)
        if fail_fast:
            raise RuntimeError(message) from error
        return False
    return True


def _clear_stale_temp_roots() -> None:
    base = _TEMP_BASE
    namespace = _NAMESPACE
    if base is None or namespace is None or not base.is_dir():
        return
    prefix = f"codex-pytest-{namespace}-"
    for candidate in base.iterdir():
        if candidate.name.startswith(prefix):
            _remove_owned_root(candidate, fail_fast=True)


def _worktree_mkdtemp(suffix=None, prefix=None, dir=None):
    """mkdtemp-compatible creation that avoids the managed ACL wrapper."""

    suffix = "" if suffix is None else suffix
    prefix = "tmp" if prefix is None else prefix
    base = Path(dir) if dir is not None else (_TEMP_ROOT or Path.cwd())
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{prefix}{uuid4().hex}{suffix}"
    path.mkdir(parents=False, exist_ok=False)
    return str(path)


class _WorktreeTemporaryDirectory(_PREVIOUS_TEMPORARY_DIRECTORY):
    """Keep the stdlib TemporaryDirectory API and finalizer behavior."""

    def cleanup(self):
        try:
            return super().cleanup()
        except PermissionError as error:
            _CLEANUP_FAILURES.append(f"temporary fixture cleanup deferred: {self.name}: {error}")
            return None


def pytest_sessionstart(session) -> None:
    global _TEMP_ROOT, _TEMP_BASE, _REPO_ROOT, _NAMESPACE

    _REPO_ROOT = Path(session.config.rootpath).resolve()
    _NAMESPACE = _namespace(_REPO_ROOT)
    _TEMP_BASE = Path(_PREVIOUS_TEMP or tempfile.gettempdir()).resolve()
    _clear_stale_temp_roots()
    _TEMP_ROOT = _TEMP_BASE / f"codex-pytest-{_NAMESPACE}-{uuid4().hex}"
    _TEMP_ROOT.mkdir(parents=True, exist_ok=False)
    (_TEMP_ROOT / _OWNER_MARKER).write_text(
        json.dumps(
            {
                "namespace": _NAMESPACE,
                "repo_root": str(_REPO_ROOT),
                "pid": os.getpid(),
                "run_id": _TEMP_ROOT.name.rsplit("-", 1)[-1],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    tempfile.tempdir = str(_TEMP_ROOT)
    tempfile.TemporaryDirectory = _WorktreeTemporaryDirectory
    tempfile.mkdtemp = _worktree_mkdtemp
    os.environ["TEMP"] = str(_TEMP_ROOT)
    os.environ["TMP"] = str(_TEMP_ROOT)


def pytest_sessionfinish(session, exitstatus: int) -> None:
    del exitstatus
    global _TEMP_ROOT

    tempfile.tempdir = _PREVIOUS_TEMP_DIR
    tempfile.TemporaryDirectory = _PREVIOUS_TEMPORARY_DIRECTORY
    tempfile.mkdtemp = _PREVIOUS_MKDTEMP
    if _PREVIOUS_TEMP is None:
        os.environ.pop("TEMP", None)
    else:
        os.environ["TEMP"] = _PREVIOUS_TEMP
    if _PREVIOUS_TMP is None:
        os.environ.pop("TMP", None)
    else:
        os.environ["TMP"] = _PREVIOUS_TMP

    if _TEMP_ROOT is not None:
        _remove_owned_root(_TEMP_ROOT, fail_fast=False)
        if _TEMP_ROOT.exists():
            _CLEANUP_FAILURES.append(f"temporary root remains after cleanup: {_TEMP_ROOT}")
        _TEMP_ROOT = None
    if _CLEANUP_FAILURES:
        print("\n".join(f"[pytest-temp] {item}" for item in _CLEANUP_FAILURES), file=sys.stderr)
        session.exitstatus = 2
