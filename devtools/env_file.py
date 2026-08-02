"""OS-independent, development-only environment file loading."""

from __future__ import annotations

import os
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import MutableMapping


_ENVIRONMENT_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_USER_ENV_FILE = Path(".config") / "kubernetes-migration-assistant" / "env"


@dataclass(frozen=True, slots=True)
class EnvFileLoadResult:
    """Safe metadata about one attempted env file load."""

    injected_keys: frozenset[str]
    selected_path: Path | None
    invalid_line_numbers: tuple[int, ...] = ()

    @property
    def loaded_keys(self) -> frozenset[str]:
        """Compatibility-friendly name for the keys injected by the loader."""

        return self.injected_keys

    @property
    def path(self) -> Path | None:
        """Compatibility-friendly name for the selected file path."""

        return self.selected_path


def _candidate_paths(
    repository_root: Path,
    explicit_path: str | Path | None,
    environment: MutableMapping[str, str],
) -> tuple[Path, ...]:
    candidates: list[Path] = []
    if explicit_path is not None and str(explicit_path).strip():
        candidates.append(Path(explicit_path).expanduser())

    configured_path = environment.get("MIGRATION_ASSISTANT_ENV_FILE", "").strip()
    if configured_path:
        candidates.append(Path(configured_path).expanduser())

    candidates.append(repository_root / ".env")
    candidates.append(Path.home() / _USER_ENV_FILE)
    return tuple(candidates)


def _select_existing_path(candidates: tuple[Path, ...]) -> Path | None:
    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate
        except OSError:
            warnings.warn(
                f"env 파일 경로를 확인할 수 없습니다: {candidate}",
                RuntimeWarning,
                stacklevel=3,
            )
            return candidate
    return None


def _parse_assignment(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].lstrip()

    if "=" not in stripped:
        return None
    raw_key, raw_value = stripped.split("=", 1)
    key = raw_key.strip()
    if _ENVIRONMENT_KEY.fullmatch(key) is None:
        return None

    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def _read_assignments(path: Path) -> tuple[dict[str, str], tuple[int, ...]]:
    try:
        contents = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        warnings.warn(
            f"env 파일을 읽을 수 없습니다: {path}",
            RuntimeWarning,
            stacklevel=3,
        )
        return {}, ()

    assignments: dict[str, str] = {}
    invalid_lines: list[int] = []
    for line_number, line in enumerate(contents.splitlines(), start=1):
        assignment = _parse_assignment(line)
        stripped = line.strip()
        if assignment is None and stripped and not stripped.startswith("#"):
            invalid_lines.append(line_number)
            warnings.warn(
                f"env 파일의 잘못된 줄을 건너뛰었습니다: {path}:{line_number}",
                RuntimeWarning,
                stacklevel=3,
            )
            continue
        if assignment is not None:
            key, value = assignment
            assignments[key] = value
    return assignments, tuple(invalid_lines)


def load_environment(
    repository_root: str | Path,
    *,
    explicit_path: str | Path | None = None,
    environment: MutableMapping[str, str] | None = None,
) -> EnvFileLoadResult:
    """Load the highest-priority existing env file without overwriting the environment."""

    target_environment = os.environ if environment is None else environment
    repository_path = Path(repository_root).expanduser()
    candidates = _candidate_paths(repository_path, explicit_path, target_environment)
    selected_path = _select_existing_path(candidates)
    if selected_path is None:
        return EnvFileLoadResult(frozenset(), None)

    assignments, invalid_line_numbers = _read_assignments(selected_path)
    injected_keys: set[str] = set()
    for key, value in assignments.items():
        if key not in target_environment:
            target_environment[key] = value
            injected_keys.add(key)
    return EnvFileLoadResult(
        injected_keys=frozenset(injected_keys),
        selected_path=selected_path,
        invalid_line_numbers=invalid_line_numbers,
    )
