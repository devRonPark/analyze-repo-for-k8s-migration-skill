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
_URL_AUTHORITY_CREDENTIAL = re.compile(
    r"(?i)(\b(?:[a-z][a-z0-9+.-]*):\/\/)([^\s\/@:]+):([^\s\/@]+)@"
)
_URL_QUERY_CREDENTIAL = re.compile(
    r"(?i)([?&;](?:user|username|password|passwd|token|api[_-]?key|access[_-]?token|secret|client[_-]?secret)=)([^&#\s;]+)"
)
_SECRET_KEY = re.compile(r"(?i)^(?:password|passwd|secret|token|api[_-]?key|private[_-]?key|access[_-]?token|client[_-]?secret)$")
_GENERIC_PLACEHOLDERS = {"", "n/a", "na", "unknown", "placeholder", "todo", "tbd"}
_OBSERVATION_EXCLUDED_DIRS = frozenset(
    {".dryforge", ".venv", "venv", "node_modules", "__pycache__", "target", "dist", "build"}
)
_OBSERVATION_EXCLUDED_FILES = frozenset({"agents.md", "skill.md", "context.md", "readme.md"})
_MAX_LINE_EVIDENCE_LINES = 4


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
    def _reject_git(cls, relative: str | Path) -> None:
        if cls._contains_git_component(relative):
            raise RepositoryToolError(".git 내부는 Repository observation 범위가 아닙니다.")

    @classmethod
    def _reject_observation_exclusion(cls, relative: str | Path) -> None:
        if cls._contains_git_component(relative):
            raise RepositoryToolError(".git 내부는 Repository observation 범위가 아닙니다.")
        parts = cls._path_components(relative)
        if any(
            part.casefold() == ".dryforge"
            and index + 1 < len(parts)
            and parts[index + 1].casefold() == "worktrees"
            for index, part in enumerate(parts)
        ):
            raise RepositoryToolError(".dryforge/worktrees 내부는 Repository observation 범위가 아닙니다.")
        if any(part.casefold() in _OBSERVATION_EXCLUDED_FILES for part in parts):
            raise RepositoryToolError("Repository instruction file은 observation 범위가 아닙니다.")
        if any(part.casefold() in _OBSERVATION_EXCLUDED_DIRS for part in parts):
            raise RepositoryToolError("생성·의존성 directory는 Repository observation 범위가 아닙니다.")

    def _begin_observation(self) -> None:
        self.budget.consume_exploration()

    def _resolve(self, relative: str | Path) -> Path:
        self._reject_observation_exclusion(relative)
        candidate = (self.repository / Path(relative)).resolve(strict=False)
        if candidate != self.repository and self.repository not in candidate.parents:
            raise RepositoryToolError("Repository 밖의 path는 읽을 수 없습니다.")
        canonical_relative = candidate.relative_to(self.repository)
        self._reject_observation_exclusion(canonical_relative)
        current = self.repository
        for part in canonical_relative.parts:
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

    def list_tree(self, relative: str = ".", max_depth: int | None = None) -> list[dict[str, object]]:
        self._begin_observation()
        root = self._resolve(relative)
        if not root.is_dir():
            raise RepositoryToolError("tree 대상은 directory여야 합니다.")
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
                    raise RepositoryToolError("symlink 또는 junction escape가 차단되었습니다.")
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
            relative_path = path.relative_to(self.repository).as_posix()
            if self._contains_observation_exclusion(relative_path):
                continue
            canonical = self._resolve(relative_path)
            if canonical.is_file():
                matches.append(canonical.relative_to(self.repository).as_posix())
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
                                "excerpt": self._redact(line),
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
                    raise RepositoryToolError("symlink 또는 junction escape가 차단되었습니다.")
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
            raise RepositoryToolError("line 범위가 올바르지 않습니다.")
        data = self._read_bytes(relative)
        path = self._resolve(relative)
        if b"\x00" in data:
            raise RepositoryToolError("binary file에는 line 근거를 만들 수 없습니다.")
        lines = self._redact(data.decode("utf-8", errors="replace")).splitlines()
        if line_start > len(lines):
            raise RepositoryToolError(
                f"line 범위가 file 범위를 벗어났습니다. 확인 가능한 마지막 line은 {len(lines)}입니다."
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
                raise RepositoryToolError("Git metadata를 읽을 수 없습니다.")
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

    def validate_analysis(self, analysis: Mapping[str, object]) -> dict[str, object]:
        self._begin_observation()
        errors: list[str] = []
        evidence_corrections: list[dict[str, object]] = []
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
        response: dict[str, object] = {"valid": not errors, "errors": errors}
        if evidence_corrections:
            response["evidence_corrections"] = evidence_corrections
        return response
