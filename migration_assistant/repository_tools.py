"""Read-only, observation-only tools for local repository analysis."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .target import BudgetExceededError, SafetyBudget
from .tool_contract import PUBLIC_AGENT_TOOL_NAMES
from .tool_protocol import ToolErrorCode, ToolIssue


PUBLIC_TOOL_NAMES = PUBLIC_AGENT_TOOL_NAMES


class RepositoryToolError(ValueError):
    """Raised when a read-only repository observation cannot be completed safely."""

    def __init__(
        self,
        message: str,
        *,
        code: ToolErrorCode = ToolErrorCode.INVALID_ARGUMENTS,
        category: str = "validation",
        field_path: str | None = None,
        retryable: bool = False,
        allowed_next_actions: tuple[str, ...] = ("validate_analysis",),
    ) -> None:
        super().__init__(message)
        self.issue = ToolIssue(
            code=code,
            category=category,
            message=message,
            field_path=field_path,
            retryable=retryable,
        )
        self.allowed_next_actions = allowed_next_actions


ToolBudget = SafetyBudget


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:password|passwd|secret|token|api[_-]?key|private[_-]?key)\b\s*[:=]\s*)([^\s#;,]+)"
)
_BEARER = re.compile(r"(?i)(\b(?:authorization\s*:\s*bearer\s+))([^\s]+)")
_URL_AUTHORITY_CREDENTIAL = re.compile(
    r"(?i)(\b(?:[a-z][a-z0-9+.-]*):\/\/)([^\s\/@:]+):([^\s\/@]+)@"
)
_URL_QUERY_CREDENTIAL = re.compile(
    r"(?i)([?&;](?:user|username|password|passwd|token|api[_-]?key|access[_-]?token|secret|client[_-]?secret)=)([^&#\s;]+)"
)
_SECRET_KEY = re.compile(r"(?i)^(?:password|passwd|secret|token|api[_-]?key|private[_-]?key|access[_-]?token|client[_-]?secret)$")
_GENERIC_PLACEHOLDERS = {"", "n/a", "na", "unknown", "placeholder", "todo", "tbd"}
_MAX_REGEX_PATTERN_LENGTH = 256
_NESTED_QUANTIFIER = re.compile(r"\((?:[^()\\]|\\.)*[+*][^()]*\)[+*{]")
_BACKREFERENCE = re.compile(r"\\(?:[1-9]|g<)")
_OBSERVATION_EXCLUDED_DIRS = frozenset(
    {".dryforge", ".venv", "venv", "node_modules", "__pycache__", "target", "dist", "build"}
)
_OBSERVATION_EXCLUDED_FILES = frozenset({"agents.md", "skill.md", "context.md", "readme.md"})
# A property block, a compose service definition or a multi-stage Dockerfile
# section rarely fits in four lines, and every rejected range costs one of the
# two recovery turns. Response size is already bounded by max_tool_response_bytes.
_MAX_LINE_EVIDENCE_LINES = 10


def redact_sensitive_text(text: str) -> str:
    """Redact credentials without changing URL structure or safe metadata."""

    text = _URL_AUTHORITY_CREDENTIAL.sub(r"\1<REDACTED>:<REDACTED>@", text)
    text = _URL_QUERY_CREDENTIAL.sub(r"\1<REDACTED>", text)
    text = _SECRET_ASSIGNMENT.sub(r"\1<REDACTED>", text)
    return _BEARER.sub(r"\1<REDACTED>", text)


def redact_sensitive_value(value: object) -> object:
    """Recursively redact strings crossing a tool, history, or artifact boundary."""

    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, Mapping):
        return {
            key: "<REDACTED>" if isinstance(key, str) and _SECRET_KEY.fullmatch(key.strip()) else redact_sensitive_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_value(item) for item in value)
    return value


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
    def _path_components(value: str | Path) -> tuple[str, ...]:
        normalized = str(value).replace("\\", "/")
        return tuple(part for part in normalized.split("/") if part not in {"", "."})

    @classmethod
    def _contains_git_component(cls, value: str | Path) -> bool:
        return any(part.casefold() == ".git" for part in cls._path_components(value))

    @classmethod
    def _contains_observation_exclusion(cls, value: str | Path) -> bool:
        parts = cls._path_components(value)
        return cls._contains_git_component(value) or any(
            part.casefold() in _OBSERVATION_EXCLUDED_FILES
            or part.casefold() in _OBSERVATION_EXCLUDED_DIRS
            or (
                part.casefold() == ".dryforge"
                and index + 1 < len(parts)
                and parts[index + 1].casefold() == "worktrees"
            )
            for index, part in enumerate(parts)
        )

    @classmethod
    def _reject_git(cls, relative: str | Path, *, field_path: str = "$.relative") -> None:
        if cls._contains_git_component(relative):
            raise RepositoryToolError(
                ".git 내부는 Repository observation 범위가 아닙니다.",
                code=ToolErrorCode.FORBIDDEN_PATH,
                category="policy",
                field_path=field_path,
            )

    @classmethod
    def _reject_observation_exclusion(cls, relative: str | Path) -> None:
        if cls._contains_git_component(relative):
            raise RepositoryToolError(
                ".git 내부는 Repository observation 범위가 아닙니다.",
                code=ToolErrorCode.FORBIDDEN_PATH,
                category="policy",
                field_path="$.relative",
            )
        parts = cls._path_components(relative)
        if any(
            part.casefold() == ".dryforge"
            and index + 1 < len(parts)
            and parts[index + 1].casefold() == "worktrees"
            for index, part in enumerate(parts)
        ):
            raise RepositoryToolError(
                ".dryforge/worktrees 내부는 Repository observation 범위가 아닙니다.",
                code=ToolErrorCode.FORBIDDEN_PATH,
                category="policy",
                field_path="$.relative",
            )
        if any(part.casefold() in _OBSERVATION_EXCLUDED_FILES for part in parts):
            raise RepositoryToolError(
                "Repository instruction file은 observation 범위가 아닙니다.",
                code=ToolErrorCode.FORBIDDEN_PATH,
                category="policy",
                field_path="$.relative",
            )
        if any(part.casefold() in _OBSERVATION_EXCLUDED_DIRS for part in parts):
            raise RepositoryToolError(
                "생성·의존성 directory는 Repository observation 범위가 아닙니다.",
                code=ToolErrorCode.FORBIDDEN_PATH,
                category="policy",
                field_path="$.relative",
            )

    def _begin_observation(self) -> None:
        self.budget.consume_exploration()

    @staticmethod
    def _exclusion_category(value: str | Path) -> str | None:
        parts = RepositoryTools._path_components(value)
        if any(part.casefold() == ".git" for part in parts):
            return "git_metadata"
        if any(part.casefold() in _OBSERVATION_EXCLUDED_FILES for part in parts):
            return "instruction_file"
        if any(part.casefold() in _OBSERVATION_EXCLUDED_DIRS for part in parts):
            return "generated_or_dependency_directory"
        return None

    @classmethod
    def _scope_meta(
        cls,
        relative: str,
        *,
        excluded_entry_count: int,
        excluded_match_count: int = 0,
        categories: set[str] | frozenset[str] = frozenset(),
    ) -> dict[str, object]:
        return {
            "requested_scope": relative,
            "scope_limited": excluded_entry_count > 0,
            "excluded_entry_count": excluded_entry_count,
            "excluded_match_count": excluded_match_count,
            "excluded_categories": sorted(categories),
        }

    @staticmethod
    def _compile_bounded_regex(pattern: object) -> re.Pattern[str]:
        if not isinstance(pattern, str) or not pattern or len(pattern) > _MAX_REGEX_PATTERN_LENGTH:
            raise RepositoryToolError(
                "검색 pattern은 비어 있지 않은 제한된 길이의 regular expression이어야 합니다.",
                code=ToolErrorCode.INVALID_ARGUMENTS,
                category="validation",
                field_path="$.pattern",
                retryable=True,
                allowed_next_actions=("search_text", "validate_analysis"),
            )
        if _NESTED_QUANTIFIER.search(pattern) or _BACKREFERENCE.search(pattern):
            raise RepositoryToolError(
                "검색 pattern이 허용된 regular expression 복잡도 한계를 초과했습니다.",
                code=ToolErrorCode.INVALID_ARGUMENTS,
                category="resource",
                field_path="$.pattern",
                retryable=True,
                allowed_next_actions=("search_text", "validate_analysis"),
            )
        try:
            return re.compile(pattern)
        except re.error as error:
            raise RepositoryToolError(
                "search pattern은 올바른 Python regular expression이어야 합니다.",
                code=ToolErrorCode.INVALID_ARGUMENTS,
                category="validation",
                field_path="$.pattern",
                retryable=True,
                allowed_next_actions=("search_text", "validate_analysis"),
            ) from error

    @classmethod
    def _scope_matches(cls, relative: str, scope: str) -> bool:
        normalized_scope = scope.replace("\\", "/").strip()
        if normalized_scope in {"", ".", "**", "**/*"}:
            return True
        normalized_path = relative.replace("\\", "/")
        if normalized_path == normalized_scope or normalized_path.startswith(normalized_scope.rstrip("/") + "/"):
            return True
        return Path(normalized_path).match(normalized_scope)

    @classmethod
    def _validate_absence_scope(cls, scope: object) -> str:
        if not isinstance(scope, str) or not scope.strip():
            raise RepositoryToolError(
                "absence_scope는 비어 있지 않은 Repository-relative 검색 범위여야 합니다.",
                code=ToolErrorCode.INVALID_ARGUMENTS,
                category="validation",
                field_path="$.absence_scope",
                retryable=True,
            )
        normalized = scope.replace("\\", "/").strip()
        if Path(normalized).is_absolute() or ".." in Path(normalized).parts or cls._contains_git_component(normalized):
            raise RepositoryToolError(
                "absence_scope는 안전한 Repository-relative 검색 범위여야 합니다.",
                code=ToolErrorCode.INVALID_ARGUMENTS,
                category="policy",
                field_path="$.absence_scope",
                retryable=True,
            )
        return normalized

    def _resolve(self, relative: str | Path) -> Path:
        self._reject_observation_exclusion(relative)
        candidate = (self.repository / Path(relative)).resolve(strict=False)
        if candidate != self.repository and self.repository not in candidate.parents:
            raise RepositoryToolError(
                "Repository 밖의 path는 읽을 수 없습니다.",
                code=ToolErrorCode.FORBIDDEN_PATH,
                category="policy",
                field_path="$.relative",
            )
        canonical_relative = candidate.relative_to(self.repository)
        self._reject_observation_exclusion(canonical_relative)
        current = self.repository
        for part in canonical_relative.parts:
            current = current / part
            if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
                raise RepositoryToolError(
                    "symlink 또는 junction escape가 차단되었습니다.",
                    code=ToolErrorCode.FORBIDDEN_PATH,
                    category="policy",
                    field_path="$.relative",
                )
        return candidate

    def _read_bytes(self, relative: str | Path) -> bytes:
        path = self._resolve(relative)
        if not path.is_file():
            raise RepositoryToolError(
                "읽을 수 있는 file이 아닙니다.",
                code=ToolErrorCode.NOT_FOUND,
                category="observation",
                field_path="$.relative",
                retryable=True,
                allowed_next_actions=("find_files", "list_tree", "validate_analysis"),
            )
        size = path.stat().st_size
        if size > self.budget.max_file_size_bytes:
            raise RepositoryToolError(
                "파일 크기 budget을 초과했습니다.",
                code=ToolErrorCode.BUDGET_EXHAUSTED,
                category="resource",
                retryable=False,
            )
        self.budget.files_seen += 1
        if self.budget.files_seen > self.budget.max_files:
            raise BudgetExceededError("파일 탐색 budget을 초과했습니다.")
        self.budget.consume_bytes(size)
        return path.read_bytes()

    def _read_bytes_for_bounded_internal_scan(self, relative: str | Path) -> bytes:
        """Read excluded bytes only for a private bounded check; never return them."""

        candidate = (self.repository / Path(relative)).resolve(strict=False)
        if candidate != self.repository and self.repository not in candidate.parents:
            raise RepositoryToolError(
                "Repository 밖의 path는 읽을 수 없습니다.",
                code=ToolErrorCode.FORBIDDEN_PATH,
                category="policy",
            )
        current = self.repository
        for part in candidate.relative_to(self.repository).parts:
            current = current / part
            if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
                raise RepositoryToolError(
                    "symlink 또는 junction escape가 차단되었습니다.",
                    code=ToolErrorCode.FORBIDDEN_PATH,
                    category="policy",
                )
        if not candidate.is_file():
            raise RepositoryToolError(
                "읽을 수 있는 file이 아닙니다.",
                code=ToolErrorCode.NOT_FOUND,
                category="observation",
            )
        size = candidate.stat().st_size
        if size > self.budget.max_file_size_bytes:
            raise BudgetExceededError("파일 크기 budget을 초과했습니다.")
        self.budget.files_seen += 1
        if self.budget.files_seen > self.budget.max_files:
            raise BudgetExceededError("파일 탐색 budget을 초과했습니다.")
        self.budget.consume_bytes(size)
        return candidate.read_bytes()

    @staticmethod
    def _redact(text: str) -> str:
        return redact_sensitive_text(text)

    redact_sensitive_text = _redact

    def inspect_target(self) -> dict[str, object]:
        self._begin_observation()
        return {
            "repository": str(self.repository),
            "repository_relative": ".",
            "read_only": True,
            "git_repository": True,
        }

    def list_tree(self, relative: str = ".", max_depth: int | None = None) -> dict[str, object]:
        self._begin_observation()
        root = self._resolve(relative)
        if not root.is_dir():
            raise RepositoryToolError(
                "tree 대상은 directory여야 합니다.",
                code=ToolErrorCode.NOT_FOUND,
                category="observation",
                field_path="$.relative",
                retryable=True,
                allowed_next_actions=("list_tree", "find_files", "validate_analysis"),
            )
        base_depth = len(root.relative_to(self.repository).parts)
        entries: list[dict[str, object]] = []
        excluded_entry_count = 0
        categories: set[str] = set()
        for current, directories, files in __import__("os").walk(root, followlinks=False):
            current_path = Path(current)
            current_relative = current_path.relative_to(self.repository)
            if self._contains_observation_exclusion(current_relative):
                continue
            allowed_directories: list[str] = []
            for directory in directories:
                relative_path = (current_path / directory).relative_to(self.repository).as_posix()
                if self._contains_observation_exclusion(relative_path):
                    excluded_entry_count += 1
                    if category := self._exclusion_category(relative_path):
                        categories.add(category)
                    continue
                allowed_directories.append(directory)
            directories[:] = allowed_directories
            depth = len(current_relative.parts) - base_depth
            if max_depth is not None and depth >= max_depth:
                directories[:] = []
            for name in sorted(directories + files):
                path = current_path / name
                relative_path = path.relative_to(self.repository).as_posix()
                if self._contains_observation_exclusion(relative_path):
                    excluded_entry_count += 1
                    if category := self._exclusion_category(relative_path):
                        categories.add(category)
                    continue
                if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                    raise RepositoryToolError(
                        "symlink 또는 junction escape가 차단되었습니다.",
                        code=ToolErrorCode.FORBIDDEN_PATH,
                        category="policy",
                        field_path="$.relative",
                    )
                entries.append({"path": relative_path, "kind": "directory" if path.is_dir() else "file"})
                if len(entries) > self.budget.max_files:
                    raise BudgetExceededError("파일 탐색 budget을 초과했습니다.")
        return {
            "entries": entries,
            "scope": self._scope_meta(
                str(relative),
                excluded_entry_count=excluded_entry_count,
                categories=categories,
            ),
        }

    def find_files(self, pattern: str) -> dict[str, object]:
        self._begin_observation()
        self._reject_git(pattern, field_path="$.pattern")
        if not pattern or Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise RepositoryToolError(
                "find pattern은 repository-relative glob이어야 합니다.",
                code=ToolErrorCode.INVALID_ARGUMENTS,
                category="validation",
                field_path="$.pattern",
                retryable=True,
                allowed_next_actions=("find_files", "list_tree", "validate_analysis"),
            )
        matches: list[str] = []
        excluded_entry_count = 0
        categories: set[str] = set()
        for path in self.repository.glob(pattern):
            relative_path = path.relative_to(self.repository).as_posix()
            if self._contains_observation_exclusion(relative_path):
                excluded_entry_count += 1
                if category := self._exclusion_category(relative_path):
                    categories.add(category)
                continue
            canonical = self._resolve(relative_path)
            if canonical.is_file():
                matches.append(canonical.relative_to(self.repository).as_posix())
        return {
            "matches": sorted(matches),
            "scope": self._scope_meta(
                pattern,
                excluded_entry_count=excluded_entry_count,
                categories=categories,
            ),
        }

    def search_text(self, pattern: str, relative: str = ".") -> dict[str, object]:
        self._begin_observation()
        self._reject_git(relative)
        matcher = self._compile_bounded_regex(pattern)
        hits: list[dict[str, object]] = []
        hit_count = 0
        excluded_entry_count = 0
        excluded_match_count = 0
        categories: set[str] = set()
        root = self._resolve(relative)
        if not root.is_dir():
            raise RepositoryToolError(
                "검색 대상은 directory여야 합니다.",
                code=ToolErrorCode.NOT_FOUND,
                category="observation",
                field_path="$.relative",
                retryable=True,
                allowed_next_actions=("list_tree", "find_files", "validate_analysis"),
            )
        for current, directories, files in __import__("os").walk(root, followlinks=False):
            current_path = Path(current)
            current_relative = current_path.relative_to(self.repository)
            if self._contains_git_component(current_relative):
                directories[:] = []
                continue
            current_excluded = self._contains_observation_exclusion(current_relative)
            if current_excluded:
                if category := self._exclusion_category(current_relative):
                    categories.add(category)
            allowed_directories: list[str] = []
            for directory in directories:
                directory_relative = (current_path / directory).relative_to(self.repository).as_posix()
                if self._contains_observation_exclusion(directory_relative):
                    excluded_entry_count += 1
                    if category := self._exclusion_category(directory_relative):
                        categories.add(category)
                if self._contains_git_component(directory_relative):
                    continue
                allowed_directories.append(directory)
            directories[:] = allowed_directories
            for name in sorted(files):
                path = current_path / name
                relative_path = path.relative_to(self.repository).as_posix()
                excluded = current_excluded or self._contains_observation_exclusion(relative_path)
                if excluded:
                    excluded_entry_count += 1
                    if category := self._exclusion_category(relative_path):
                        categories.add(category)
                if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                    raise RepositoryToolError(
                        "symlink 또는 junction escape가 차단되었습니다.",
                        code=ToolErrorCode.FORBIDDEN_PATH,
                        category="policy",
                        field_path="$.relative",
                    )
                data = (
                    self._read_bytes_for_bounded_internal_scan(relative_path)
                    if excluded
                    else self._read_bytes(relative_path)
                )
                if b"\x00" in data:
                    continue
                text = data.decode("utf-8", errors="replace")
                file_match_count = 0
                for line_number, line in enumerate(text.splitlines(), 1):
                    if matcher.search(line):
                        file_match_count += 1
                        if not excluded and len(hits) < self.budget.max_search_results:
                            hits.append(
                                {
                                    "path": relative_path,
                                    "line_start": line_number,
                                    "line_end": line_number,
                                    "text": self._redact(line),
                                    "excerpt": self._redact(line),
                                }
                            )
                if excluded:
                    excluded_match_count += file_match_count
                else:
                    hit_count += file_match_count
        return {
            "hits": hits,
            "hit_count": hit_count,
            "returned_hit_count": len(hits),
            "truncated": hit_count > len(hits),
            "scope": self._scope_meta(
                str(relative),
                excluded_entry_count=excluded_entry_count,
                excluded_match_count=excluded_match_count,
                categories=categories,
            ),
        }

    def _list_tree(self, relative: str = ".", max_depth: int | None = None) -> list[dict[str, object]]:
        root = self._resolve(relative)
        if not root.is_dir():
            raise RepositoryToolError(
                "tree 대상은 directory여야 합니다.",
                code=ToolErrorCode.NOT_FOUND,
                category="observation",
                field_path="$.relative",
                retryable=True,
                allowed_next_actions=("list_tree", "find_files", "validate_analysis"),
            )
        base_depth = len(root.relative_to(self.repository).parts)
        entries: list[dict[str, object]] = []
        for current, directories, files in __import__("os").walk(root, followlinks=False):
            current_path = Path(current)
            current_relative = current_path.relative_to(self.repository)
            if self._contains_observation_exclusion(current_relative):
                continue
            directories[:] = [directory for directory in directories if directory.casefold() != ".git"]
            depth = len(current_relative.parts) - base_depth
            if max_depth is not None and depth >= max_depth:
                directories[:] = []
            for name in sorted(directories + files):
                path = current_path / name
                relative_path = path.relative_to(self.repository).as_posix()
                if self._contains_observation_exclusion(relative_path):
                    continue
                if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                    raise RepositoryToolError(
                        "symlink 또는 junction escape가 차단되었습니다.",
                        code=ToolErrorCode.FORBIDDEN_PATH,
                        category="policy",
                        field_path="$.relative",
                    )
                entries.append({"path": relative_path, "kind": "directory" if path.is_dir() else "file"})
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
            raise RepositoryToolError(
                "line 범위가 올바르지 않습니다.",
                code=ToolErrorCode.INVALID_ARGUMENTS,
                category="validation",
                field_path="$.line_end",
                retryable=True,
                allowed_next_actions=("read_file_lines", "validate_analysis"),
            )
        data = self._read_bytes(relative)
        path = self._resolve(relative)
        if b"\x00" in data:
            raise RepositoryToolError(
                "binary file에는 line 근거를 만들 수 없습니다.",
                code=ToolErrorCode.INVALID_ARGUMENTS,
                category="validation",
                field_path="$.relative",
                retryable=False,
            )
        lines = self._redact(data.decode("utf-8", errors="replace")).splitlines()
        if line_start > len(lines):
            raise RepositoryToolError(
                f"line 범위가 file 범위를 벗어났습니다. 확인 가능한 마지막 line은 {len(lines)}입니다.",
                code=ToolErrorCode.NOT_FOUND,
                category="observation",
                field_path="$.line_start",
                retryable=True,
                allowed_next_actions=("search_text", "read_file_lines", "validate_analysis"),
            )
        effective_end = min(
            line_end,
            line_start + min(self.budget.max_search_results, _MAX_LINE_EVIDENCE_LINES) - 1,
            len(lines),
        )
        return [
            {
                "path": path.relative_to(self.repository).as_posix(),
                "line_start": number,
                "line_end": number,
                "text": lines[number - 1],
                "excerpt": lines[number - 1],
            }
            for number in range(line_start, effective_end + 1)
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
                raise RepositoryToolError(
                    "Git metadata를 읽을 수 없습니다.",
                    code=ToolErrorCode.NOT_FOUND,
                    category="observation",
                    retryable=False,
                )
            return result.stdout.strip()

        return {
            "branch": self._redact(git("branch", "--show-current")),
            "head": self._redact(git("rev-parse", "HEAD")),
            "status": self._redact(git("status", "--short")),
            "remotes": sorted(
                {
                    self._redact(parts[1])
                    for line in git("remote", "-v").splitlines()
                    if len(parts := line.split()) >= 2
                }
            ),
        }

    @staticmethod
    def _compact(value: str) -> str:
        return re.sub(r"\s+", "", value)

    @classmethod
    def _meaningful(cls, value: object) -> bool:
        if not isinstance(value, str):
            return False
        return value.strip().casefold() not in _GENERIC_PLACEHOLDERS

    @classmethod
    def _existence_only_claim(cls, value: str) -> bool:
        normalized = " ".join(value.casefold().split())
        return normalized in {"file exists", "path exists", "파일이 존재한다", "파일이 존재함", "파일 존재"}

    @staticmethod
    def _absence_issue(
        code: str,
        evidence_index: int,
        message: str,
        *,
        field_path: str | None = None,
    ) -> dict[str, object]:
        return {
            "code": code,
            "evidence_index": evidence_index,
            "field_path": field_path or f"$.evidence[{evidence_index}]",
            "message": message,
        }

    def _verify_absence(self, evidence_index: int, item: Mapping[str, object]) -> tuple[list[dict[str, object]], dict[str, object] | None]:
        scope = item.get("absence_scope")
        pattern = item.get("absence_pattern")
        try:
            normalized_scope = self._validate_absence_scope(scope)
        except RepositoryToolError:
            return [
                self._absence_issue(
                    "absence_scope_invalid",
                    evidence_index,
                    "unresolved absence evidence의 검색 범위를 검증할 수 없습니다.",
                    field_path=f"$.evidence[{evidence_index}].absence_scope",
                )
            ], None
        try:
            matcher = self._compile_bounded_regex(pattern)
        except RepositoryToolError:
            return [
                self._absence_issue(
                    "absence_pattern_invalid",
                    evidence_index,
                    "unresolved absence evidence의 검색 pattern이 유효하거나 bounded하지 않습니다.",
                    field_path=f"$.evidence[{evidence_index}].absence_pattern",
                )
            ], None

        try:
            for current, directories, files in __import__("os").walk(self.repository, followlinks=False):
                current_path = Path(current)
                current_relative = current_path.relative_to(self.repository)
                directories[:] = [
                    directory
                    for directory in directories
                    if not self._contains_git_component(current_relative / directory)
                ]
                for name in sorted(files):
                    path = current_path / name
                    relative_path = path.relative_to(self.repository).as_posix()
                    if self._contains_git_component(relative_path) or not self._scope_matches(relative_path, normalized_scope):
                        continue
                    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                        raise RepositoryToolError(
                            "symlink 또는 junction escape가 차단되었습니다.",
                            code=ToolErrorCode.FORBIDDEN_PATH,
                            category="policy",
                        )
                    data = self._read_bytes_for_bounded_internal_scan(relative_path)
                    if b"\x00" in data:
                        continue
                    text = data.decode("utf-8", errors="replace")
                    if any(matcher.search(line) for line in text.splitlines()):
                        return [
                            self._absence_issue(
                                "absence_contradicted",
                                evidence_index,
                                "unresolved absence evidence가 Repository 관찰과 모순됩니다.",
                            )
                        ], {
                            "index": evidence_index,
                            "action": "recheck_absence_evidence",
                            "reason": "declared absence was contradicted by the repository scan",
                        }
        except BudgetExceededError:
            return [
                self._absence_issue(
                    "absence_unverified",
                    evidence_index,
                    "탐색 budget 안에서 unresolved absence evidence를 재검증하지 못했습니다.",
                )
            ], {
                "index": evidence_index,
                "action": "do_not_accept_as_verified",
                "reason": "absence verification exceeded the exploration budget",
            }
        except RepositoryToolError:
            return [
                self._absence_issue(
                    "absence_unverified",
                    evidence_index,
                    "안전한 Repository 재검증을 완료하지 못해 unresolved absence evidence를 확인할 수 없습니다.",
                )
            ], {
                "index": evidence_index,
                "action": "do_not_accept_as_verified",
                "reason": "the absence verification scan could not safely complete",
            }
        return [], None

    def validate_analysis(self, analysis: Mapping[str, object]) -> dict[str, object]:
        self._begin_observation()
        errors: list[str] = []
        issues: list[dict[str, object]] = []
        evidence_corrections: list[dict[str, object]] = []
        absence_corrections: list[dict[str, object]] = []
        evidence = analysis.get("evidence") if isinstance(analysis, Mapping) else None
        findings = analysis.get("findings") if isinstance(analysis, Mapping) else None
        status = analysis.get("status") if isinstance(analysis, Mapping) else None
        errors_field = analysis.get("errors") if isinstance(analysis, Mapping) else None
        if status == "complete" and errors_field:
            errors.append("complete 결과의 errors에는 외부 선택이나 process 오류를 넣지 말고 structured unresolved decision을 사용하세요.")
        if not isinstance(evidence, list):
            errors.append("evidence는 list여야 합니다.")
        else:
            evidence_ids: set[str] = set()
            for evidence_index, item in enumerate(evidence):
                if not isinstance(item, Mapping):
                    errors.append("evidence 항목은 mapping이어야 합니다.")
                    continue
                evidence_id = item.get("id")
                path = item.get("path")
                start = item.get("line_start")
                end = item.get("line_end")
                if item.get("status") == "unresolved":
                    if not all(self._meaningful(item.get(key)) for key in ("absence_scope", "absence_pattern", "result")):
                        errors.append("unresolved evidence에는 scope, pattern, result가 필요합니다.")
                    else:
                        absence_issues, correction = self._verify_absence(evidence_index, item)
                        issues.extend(absence_issues)
                        if correction is not None:
                            absence_corrections.append(correction)
                        if absence_issues:
                            errors.append("unresolved absence evidence를 Repository와 대조하지 못했거나 모순이 발견되었습니다.")
                    continue
                claim = item.get("claim")
                excerpt = item.get("text") if item.get("text") is not None else item.get("excerpt")
                if not isinstance(path, str) or not isinstance(start, int) or not isinstance(end, int):
                    errors.append("positive evidence에는 path와 line 범위가 필요합니다.")
                    continue
                if not isinstance(evidence_id, str) or not evidence_id.strip() or evidence_id in evidence_ids:
                    errors.append("positive evidence에는 고유한 id가 필요합니다.")
                elif evidence_id:
                    evidence_ids.add(evidence_id)
                if not self._meaningful(claim) or self._existence_only_claim(str(claim)):
                    errors.append(f"evidence claim이 비어 있거나 file existence만 주장합니다: {path}")
                if not self._meaningful(excerpt):
                    errors.append(f"evidence excerpt가 비어 있거나 placeholder입니다: {path}")
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
                        lines = self._redact(self._read_bytes(path).decode("utf-8", errors="replace")).splitlines()
                        if end > len(lines):
                            errors.append(f"evidence line 범위가 file 범위를 벗어났습니다: {path}")
                            if start <= len(lines):
                                evidence_corrections.append(
                                    {
                                        "index": evidence_index,
                                        "id": evidence_id,
                                        "path": path,
                                        "line_start": start,
                                        "line_end": len(lines),
                                        "excerpt": "\n".join(lines[start - 1 :]),
                                    }
                                )
                        else:
                            actual = "\n".join(lines[start - 1 : end])
                            if self._compact(str(excerpt)) not in self._compact(actual):
                                errors.append(f"evidence excerpt가 실제 Repository line과 일치하지 않습니다: {path}:{start}-{end}")
                                evidence_corrections.append(
                                    {
                                        "index": evidence_index,
                                        "id": evidence_id,
                                        "path": path,
                                        "line_start": start,
                                        "line_end": end,
                                        "excerpt": actual,
                                    }
                                )
                    except RepositoryToolError as error:
                        errors.append(str(error))
        positive_finding = False
        if not isinstance(findings, list):
            errors.append("findings는 list여야 합니다.")
        else:
            finding_ids: set[str] = set()
            evidence_ids = {
                item.get("id") for item in evidence or [] if isinstance(item, Mapping) and isinstance(item.get("id"), str)
            }
            for finding in findings:
                if not isinstance(finding, Mapping):
                    errors.append("finding 항목은 mapping이어야 합니다.")
                    continue
                finding_id = finding.get("id")
                if not isinstance(finding_id, str) or not finding_id.strip() or finding_id in finding_ids:
                    errors.append("finding에는 고유한 id가 필요합니다.")
                else:
                    finding_ids.add(finding_id)
                if not self._meaningful(finding.get("claim")):
                    errors.append("finding claim은 비어 있을 수 없습니다.")
                finding_status = finding.get("status")
                refs = finding.get("evidence_ids")
                if finding_status == "unresolved":
                    if finding.get("resolution_owner") not in {"repository", "user", "deployment_environment", "external_system"}:
                        errors.append("unresolved finding에는 유효한 resolution_owner가 필요합니다.")
                    if not all(self._meaningful(finding.get(key)) for key in ("resolution_source", "reason")):
                        errors.append("unresolved finding에는 resolution_source와 reason이 필요합니다.")
                else:
                    positive_finding = True
                    if not isinstance(refs, list) or not refs or any(ref not in evidence_ids for ref in refs):
                        errors.append("positive finding은 존재하는 evidence id를 하나 이상 참조해야 합니다.")
        if status == "complete" and not positive_finding:
            errors.append("complete 결과에는 valid positive Evidence를 참조하는 finding이 필요합니다.")
        response: dict[str, object] = {"valid": not errors, "errors": errors, "issues": issues}
        if evidence_corrections:
            response["evidence_corrections"] = evidence_corrections
        if absence_corrections:
            response["absence_corrections"] = absence_corrections
        return response
