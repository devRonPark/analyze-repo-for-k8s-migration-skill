"""Non-blocking, fail-open PostToolUse integration for code-review-graph."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import BinaryIO, Sequence


LOCK_FILENAME = "post_tool_update.lock"
LOG_FILENAME = "post_tool_update.log"
DEFAULT_TIMEOUT_SECONDS = 30
STALE_LOCK_SECONDS = 120


def drain_stdin(stream: BinaryIO | None) -> None:
    """Consume the hook payload so the caller cannot hit a broken pipe."""
    if stream is None:
        return
    while stream.read(64 * 1024):
        pass


def _process_stdin() -> BinaryIO | None:
    stream = getattr(sys, "stdin", None)
    if stream is None:
        return None
    return getattr(stream, "buffer", stream)


def _repo_path(value: str | None) -> Path:
    root = Path(value).resolve() if value else Path(__file__).resolve().parents[1]
    return root


def _graph_dir(repo: Path) -> Path:
    return repo / ".code-review-graph"


def _lock_path(repo: Path) -> Path:
    return _graph_dir(repo) / LOCK_FILENAME


def _log_path(repo: Path) -> Path:
    return _graph_dir(repo) / LOG_FILENAME


def _append_log(repo: Path, message: str) -> None:
    try:
        _graph_dir(repo).mkdir(parents=True, exist_ok=True)
        with _log_path(repo).open("a", encoding="utf-8") as log:
            log.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {message}\n")
    except OSError:
        pass


def _acquire_lock(repo: Path) -> bool:
    lock_path = _lock_path(repo)
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with lock_path.open("x", encoding="ascii") as lock:
                lock.write(str(os.getpid()))
            return True
        except FileExistsError:
            age = time.time() - lock_path.stat().st_mtime
            if age <= STALE_LOCK_SECONDS:
                return False
            lock_path.unlink(missing_ok=True)
            with lock_path.open("x", encoding="ascii") as lock:
                lock.write(str(os.getpid()))
            return True
    except OSError:
        return False


def _release_lock(repo: Path) -> None:
    try:
        _lock_path(repo).unlink(missing_ok=True)
    except OSError:
        pass


def _resolve_crg_executable(explicit: str | None) -> str:
    candidates = [explicit, os.environ.get("CRG_EXECUTABLE")]
    sibling = Path(sys.executable).with_name(
        "code-review-graph.exe" if os.name == "nt" else "code-review-graph"
    )
    candidates.append(str(sibling))
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(
                str(Path(appdata) / "uv" / "tools" / "code-review-graph" / "Scripts" / "code-review-graph.exe")
            )
    candidates.append(shutil.which("code-review-graph"))
    for candidate in candidates:
        if candidate and (Path(candidate).exists() or shutil.which(candidate)):
            return candidate
    return candidates[0] or "code-review-graph"


def _spawn_worker(repo: Path, timeout_seconds: int, crg_executable: str | None) -> None:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--repo",
        str(repo),
        "--timeout-seconds",
        str(timeout_seconds),
    ]
    if crg_executable:
        command.extend(["--crg-executable", crg_executable])
    log_handle = None
    try:
        _graph_dir(repo).mkdir(parents=True, exist_ok=True)
        log_handle = _log_path(repo).open("a", encoding="utf-8")
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        subprocess.Popen(
            command,
            cwd=repo,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            # Do not let the Codex/Claude hook pipe remain open in the
            # detached worker. Otherwise Windows callers can wait for the
            # worker's inherited handle even though the hook has returned.
            close_fds=True,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
    except (OSError, ValueError) as exc:
        _append_log(repo, f"hook worker launch skipped: {exc}")
        _release_lock(repo)
    finally:
        if log_handle is not None:
            log_handle.close()


def _run_worker(repo: Path, timeout_seconds: int, crg_executable: str | None) -> int:
    try:
        executable = _resolve_crg_executable(crg_executable)
        _append_log(repo, f"update started: {executable}")
        completed = subprocess.run(
            [executable, "update", "--skip-flows"],
            cwd=repo,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        output = completed.stdout.strip()
        if output:
            _append_log(repo, output)
        _append_log(repo, f"update finished: exit={completed.returncode}")
    except Exception as exc:  # Hook refresh is optional and must never fail the tool.
        _append_log(repo, f"update failed open: {type(exc).__name__}: {exc}")
    finally:
        _release_lock(repo)
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: BinaryIO | None = None,
) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--crg-executable")
    args = parser.parse_args(argv)
    drain_stdin(stdin if stdin is not None else _process_stdin())
    repo = _repo_path(args.repo)

    if args.worker:
        return _run_worker(repo, max(1, args.timeout_seconds), args.crg_executable)
    if not (_graph_dir(repo) / "graph.db").exists():
        return 0
    if not _acquire_lock(repo):
        return 0
    _spawn_worker(repo, max(1, args.timeout_seconds), args.crg_executable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
