"""Read-only, observation-only tools for local repository analysis."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .target import BudgetExceededError, SafetyBudget
from .tool_contract import PUBLIC_AGENT_TOOL_NAMES


PUBLIC_TOOL_NAMES = PUBLIC_AGENT_TOOL_NAMES


class RepositoryToolError(ValueError):
    """Raised when a read-only repository observation cannot be completed safely."""


ToolBudget = SafetyBudget


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:password|passwd|secret|token|api[_-]?key|private[_-]?key)\b\s*[:=]\s*)([^\s#;,]+)"
)
_BEARER = re.compile(r"(?i)(\b(?:authorization\s*:\s*bearer\s+))([^\s]+)")


class RepositoryTools:
    """Expose bounded repository facts without running repository code."""

    def __init__(self, repository: str | Path, budget: ToolBudget | None = None) -> None:
        self.repository = Path(repository).expanduser().resolve(strict=True)
        if not self.repository.is_dir():
            raise RepositoryToolError("입력 Repository는 directory여야 합니다.")
        git = subprocess.run(
            ["git", "-C", str(self.repository), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
        if git.returncode != 0 or git.stdout.strip().lower() != "true":
            raise RepositoryToolError("입력 경로가 유효한 Git repository가 아닙니다.")
        self.budget = budget or ToolBudget()

    @staticmethod
    def _reject_git(relative: str | Path) -> None:
        parts = Path(relative).parts
        if ".git" in parts:
            raise RepositoryToolError(".git 내부는 Repository observation 범위가 아닙니다.")

    def _begin_observation(self) -> None:
        self.budget.consume_exploration()

    def _resolve(self, relative: str | Path) -> Path:
        self._reject_git(relative)
        candidate = (self.repository / Path(relative)).resolve(strict=False)
        if candidate != self.repository and self.repository not in candidate.parents:
            raise RepositoryToolError("Repository 밖의 path는 읽을 수 없습니다.")
        current = self.repository
        for part in candidate.relative_to(self.repository).parts:
            current = current / part
            if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
                raise RepositoryToolError("symlink 또는 junction escape가 차단되었습니다.")
        return candidate

    def _read_bytes(self, relative: str | Path) -> bytes:
        path = self._resolve(relative)
        if not path.is_file():
            raise RepositoryToolError("읽을 수 있는 file이 아닙니다.")
        size = path.stat().st_size
        if size > self.budget.max_file_size_bytes:
            raise RepositoryToolError("파일 크기 budget을 초과했습니다.")
        self.budget.files_seen += 1
        if self.budget.files_seen > self.budget.max_files:
            raise BudgetExceededError("파일 탐색 budget을 초과했습니다.")
        self.budget.consume_bytes(size)
        return path.read_bytes()

    @staticmethod
    def _redact(text: str) -> str:
        text = _SECRET_ASSIGNMENT.sub(r"\1<REDACTED>", text)
        return _BEARER.sub(r"\1<REDACTED>", text)

    def inspect_target(self) -> dict[str, object]:
        self._begin_observation()
        return {
            "repository": str(self.repository),
            "repository_relative": ".",
            "read_only": True,
            "git_repository": True,
        }

    def list_tree(self, relative: str = ".", max_depth: int | None = None) -> list[dict[str, object]]:
        self._begin_observation()
        root = self._resolve(relative)
        if not root.is_dir():
            raise RepositoryToolError("tree 대상은 directory여야 합니다.")
        base_depth = len(root.relative_to(self.repository).parts)
        entries: list[dict[str, object]] = []
        for current, directories, files in __import__("os").walk(root, followlinks=False):
            current_path = Path(current)
            if ".git" in current_path.relative_to(self.repository).parts:
                continue
            directories[:] = [directory for directory in directories if directory != ".git"]
            depth = len(current_path.relative_to(self.repository).parts) - base_depth
            if max_depth is not None and depth >= max_depth:
                directories[:] = []
            for name in sorted(directories + files):
                path = current_path / name
                if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                    raise RepositoryToolError("symlink 또는 junction escape가 차단되었습니다.")
                relative_path = path.relative_to(self.repository).as_posix()
                entries.append({"path": relative_path, "kind": "directory" if path.is_dir() else "file"})
                if len(entries) > self.budget.max_files:
                    raise BudgetExceededError("파일 탐색 budget을 초과했습니다.")
        return entries

    def find_files(self, pattern: str) -> list[str]:
        self._begin_observation()
        self._reject_git(pattern)
        if not pattern or Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise RepositoryToolError("find pattern은 repository-relative여야 합니다.")
        matches: list[str] = []
        for path in self.repository.glob(pattern):
            if ".git" in path.relative_to(self.repository).parts:
                continue
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise RepositoryToolError("symlink 또는 junction escape가 차단되었습니다.")
            if path.is_file():
                matches.append(path.relative_to(self.repository).as_posix())
        return sorted(matches)

    def search_text(self, pattern: str, relative: str = ".") -> dict[str, object]:
        self._begin_observation()
        self._reject_git(relative)
        try:
            matcher = re.compile(pattern)
        except re.error as error:
            raise RepositoryToolError("search pattern이 올바르지 않습니다.") from error
        hits: list[dict[str, object]] = []
        hit_count = 0
        for path in self._list_tree(relative):
            if path["kind"] != "file":
                continue
            data = self._read_bytes(str(path["path"]))
            if b"\x00" in data:
                continue
            text = data.decode("utf-8", errors="replace")
            for line_number, line in enumerate(text.splitlines(), 1):
                if matcher.search(line):
                    hit_count += 1
                    if len(hits) < self.budget.max_search_results:
                        hits.append(
                            {
                                "path": str(path["path"]),
                                "line_start": line_number,
                                "line_end": line_number,
                                "text": self._redact(line),
                            }
                        )
        return {"hits": hits, "hit_count": hit_count, "returned_hit_count": len(hits), "truncated": hit_count > len(hits)}

    def _list_tree(self, relative: str = ".", max_depth: int | None = None) -> list[dict[str, object]]:
        root = self._resolve(relative)
        if not root.is_dir():
            raise RepositoryToolError("tree 대상은 directory여야 합니다.")
        base_depth = len(root.relative_to(self.repository).parts)
        entries: list[dict[str, object]] = []
        for current, directories, files in __import__("os").walk(root, followlinks=False):
            current_path = Path(current)
            if ".git" in current_path.relative_to(self.repository).parts:
                continue
            directories[:] = [directory for directory in directories if directory != ".git"]
            depth = len(current_path.relative_to(self.repository).parts) - base_depth
            if max_depth is not None and depth >= max_depth:
                directories[:] = []
            for name in sorted(directories + files):
                path = current_path / name
                if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                    raise RepositoryToolError("symlink 또는 junction escape가 차단되었습니다.")
                entries.append({"path": path.relative_to(self.repository).as_posix(), "kind": "directory" if path.is_dir() else "file"})
                if len(entries) > self.budget.max_files:
                    raise BudgetExceededError("파일 탐색 budget을 초과했습니다.")
        return entries

    def read_file(self, relative: str) -> dict[str, object]:
        self._begin_observation()
        data = self._read_bytes(relative)
        path = self._resolve(relative)
        if b"\x00" in data:
            return {"path": path.relative_to(self.repository).as_posix(), "binary": True}
        text = self._redact(data.decode("utf-8", errors="replace"))
        encoded = text.encode("utf-8")
        truncated = len(encoded) > self.budget.max_tool_response_bytes
        if truncated:
            text = encoded[: self.budget.max_tool_response_bytes].decode("utf-8", errors="ignore")
        return {
            "path": path.relative_to(self.repository).as_posix(),
            "binary": False,
            "text": text,
            "returned_bytes": len(text.encode("utf-8")),
            "truncated": truncated,
        }

    def read_file_lines(self, relative: str, line_start: int, line_end: int) -> list[dict[str, object]]:
        self._begin_observation()
        if line_start < 1 or line_end < line_start:
            raise RepositoryToolError("line 범위가 올바르지 않습니다.")
        if line_end - line_start + 1 > self.budget.max_search_results:
            raise BudgetExceededError("line evidence 응답 크기 budget을 초과했습니다.")
        data = self._read_bytes(relative)
        path = self._resolve(relative)
        if b"\x00" in data:
            raise RepositoryToolError("binary file에는 line 근거를 만들 수 없습니다.")
        lines = self._redact(data.decode("utf-8", errors="replace")).splitlines()
        if line_end > len(lines):
            raise RepositoryToolError("line 범위가 file 범위를 벗어났습니다.")
        return [
            {
                "path": path.relative_to(self.repository).as_posix(),
                "line_start": number,
                "line_end": number,
                "text": lines[number - 1],
            }
            for number in range(line_start, line_end + 1)
        ]

    def inspect_git_metadata(self) -> dict[str, object]:
        self._begin_observation()
        def git(*args: str) -> str:
            result = subprocess.run(
                ["git", "-C", str(self.repository), *args],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise RepositoryToolError("Git metadata를 읽을 수 없습니다.")
            return result.stdout.strip()

        return {
            "branch": self._redact(git("branch", "--show-current")),
            "head": self._redact(git("rev-parse", "HEAD")),
            "status": self._redact(git("status", "--short")),
        }

    def validate_analysis(self, analysis: Mapping[str, object]) -> dict[str, object]:
        self._begin_observation()
        errors: list[str] = []
        evidence = analysis.get("evidence") if isinstance(analysis, Mapping) else None
        if not isinstance(evidence, list):
            errors.append("evidence는 list여야 합니다.")
        else:
            for item in evidence:
                if not isinstance(item, Mapping):
                    errors.append("evidence 항목은 mapping이어야 합니다.")
                    continue
                path = item.get("path")
                start = item.get("line_start")
                end = item.get("line_end")
                if item.get("status") == "unresolved":
                    if not isinstance(item.get("absence_scope"), str) or not isinstance(item.get("absence_pattern"), str) or not isinstance(item.get("result"), str):
                        errors.append("unresolved evidence에는 scope, pattern, result가 필요합니다.")
                    continue
                if not isinstance(path, str) or not isinstance(start, int) or not isinstance(end, int):
                    errors.append("evidence에는 path와 line 범위가 필요합니다.")
                    continue
                try:
                    target = self._resolve(path)
                except RepositoryToolError as error:
                    errors.append(str(error))
                    continue
                if not target.is_file():
                    errors.append(f"evidence path가 없습니다: {path}")
                elif start < 1 or end < start:
                    errors.append(f"evidence line 범위가 올바르지 않습니다: {path}")
                else:
                    try:
                        lines = self._read_bytes(path).decode("utf-8", errors="replace").splitlines()
                        if end > len(lines):
                            errors.append(f"evidence line 범위가 file 범위를 벗어났습니다: {path}")
                    except RepositoryToolError as error:
                        errors.append(str(error))
        return {"valid": not errors, "errors": errors}
