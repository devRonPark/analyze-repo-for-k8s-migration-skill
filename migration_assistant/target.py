"""Deterministic read-only target and output safety boundary."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator


class TargetSafetyError(ValueError):
    """Raised when a repository or output path violates a safety rule."""


class BudgetExceededError(TargetSafetyError):
    """Raised when a configured exploration budget is exhausted."""


@dataclass
class SafetyBudget:
    max_file_size_bytes: int = 10 * 1024 * 1024
    max_files: int = 10_000
    max_explorations: int = 100
    max_iterations: int = 50
    max_total_bytes: int = 100 * 1024 * 1024
    max_search_results: int = 32
    max_no_progress: int = 3
    max_tool_response_bytes: int = 32 * 1024
    files_seen: int = 0
    explorations: int = 0
    iterations: int = 0
    total_bytes: int = 0

    def consume_exploration(self) -> None:
        self.explorations += 1
        if self.explorations > self.max_explorations:
            raise BudgetExceededError("탐색 budget을 초과했습니다.")

    def consume_iteration(self) -> None:
        self.iterations += 1
        if self.iterations > self.max_iterations:
            raise BudgetExceededError("iteration budget을 초과했습니다.")

    def consume_bytes(self, size: int) -> None:
        if size < 0 or self.total_bytes + size > self.max_total_bytes:
            raise BudgetExceededError("전체 file bytes budget을 초과했습니다.")
        self.total_bytes += size


@dataclass
class OutputTransaction:
    path: Path
    _complete: bool = field(default=False, init=False)

    def mark_complete(self) -> None:
        self._complete = True

    def cleanup(self) -> None:
        if self._complete or not self.path.exists():
            return
        shutil.rmtree(self.path)


@dataclass
class TargetSafetyGate:
    repository: Path
    budget: SafetyBudget = field(default_factory=SafetyBudget)
    output_path: Path | None = None

    @classmethod
    def open(
        cls,
        repository: str | os.PathLike[str],
        output_path: str | os.PathLike[str] | None = None,
        budget: SafetyBudget | None = None,
    ) -> "TargetSafetyGate":
        root = Path(repository).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise TargetSafetyError("입력 경로는 directory여야 합니다.")
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        git_root = (
            Path(result.stdout.strip()).expanduser().resolve(strict=False)
            if result.returncode == 0 and result.stdout.strip()
            else None
        )
        if result.returncode != 0 or git_root != root:
            raise TargetSafetyError("입력 경로가 유효한 Git repository가 아닙니다.")

        canonical_output = None
        if output_path is not None:
            raw_candidate = Path(output_path).expanduser().absolute()
            cls._assert_no_link_components(raw_candidate)
            candidate = raw_candidate.resolve(strict=False)
            if candidate.exists():
                raise TargetSafetyError("지정한 output directory가 이미 존재합니다.")
            if candidate == root or root in candidate.parents:
                raise TargetSafetyError("output은 Repository 내부일 수 없습니다.")
            if candidate in root.parents:
                raise TargetSafetyError("output이 Repository를 포함하는 상위 경로입니다.")
            cls._assert_no_link_components(candidate)
            canonical_output = candidate
        return cls(root, budget or SafetyBudget(), canonical_output)

    def _safe_path(self, relative: str | os.PathLike[str]) -> Path:
        candidate = (self.repository / Path(relative)).resolve(strict=False)
        if candidate != self.repository and self.repository not in candidate.parents:
            raise TargetSafetyError("Repository 밖의 path는 읽을 수 없습니다.")
        current = self.repository
        for part in candidate.relative_to(self.repository).parts:
            current = current / part
            if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
                raise TargetSafetyError("symlink 또는 junction escape가 차단되었습니다.")
        return candidate

    def read_file(self, relative: str | os.PathLike[str]) -> bytes:
        path = self._safe_path(relative)
        if not path.is_file():
            raise TargetSafetyError("읽을 수 있는 file이 아닙니다.")
        size = path.stat().st_size
        if size > self.budget.max_file_size_bytes:
            raise BudgetExceededError("파일 크기 budget을 초과했습니다.")
        self.consume_bytes(size)
        return path.read_bytes()

    def iter_files(self) -> Iterator[Path]:
        for current, directories, files in os.walk(self.repository, followlinks=False):
            current_path = Path(current)
            for directory in list(directories):
                path = current_path / directory
                if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                    raise TargetSafetyError("symlink 또는 junction escape가 차단되었습니다.")
            for filename in files:
                path = current_path / filename
                self.budget.files_seen += 1
                if self.budget.files_seen > self.budget.max_files:
                    raise BudgetExceededError("파일 탐색 budget을 초과했습니다.")
                self._safe_path(path.relative_to(self.repository))
                yield path

    def consume_exploration(self) -> None:
        self.budget.consume_exploration()

    def consume_iteration(self) -> None:
        self.budget.consume_iteration()

    def consume_bytes(self, size: int) -> None:
        self.budget.consume_bytes(size)

    @staticmethod
    def _assert_no_link_components(path: Path) -> None:
        for component in reversed(path.parents):
            if component.exists() and (component.is_symlink() or getattr(component, "is_junction", lambda: False)()):
                raise TargetSafetyError("symlink 또는 junction output 경로가 차단되었습니다.")
        if path.exists() and (path.is_symlink() or getattr(path, "is_junction", lambda: False)()):
            raise TargetSafetyError("symlink 또는 junction output 경로가 차단되었습니다.")

    def create_output(self) -> OutputTransaction:
        output = self.output_path
        if output is None:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            output = self.repository.parent / f"{self.repository.name}-k8s-output-{stamp}"
            suffix = 1
            while output.exists():
                output = self.repository.parent / (
                    f"{self.repository.name}-k8s-output-{stamp}-{suffix}"
                )
                suffix += 1
        elif output.exists():
            raise TargetSafetyError("지정한 output directory가 이미 존재합니다.")
        output = output.resolve(strict=False)
        if output == self.repository or self.repository in output.parents or output in self.repository.parents:
            raise TargetSafetyError("output은 Repository 내부 또는 Repository를 포함하는 상위 경로일 수 없습니다.")
        self._assert_no_link_components(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            output.mkdir()
        except FileExistsError as error:
            raise TargetSafetyError("output directory를 exclusive하게 만들 수 없습니다.") from error
        return OutputTransaction(output)
