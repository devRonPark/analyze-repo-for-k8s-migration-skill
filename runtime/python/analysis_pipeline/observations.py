"""Process-private trusted observations and fail-closed target snapshots."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import secrets
from typing import Any, Mapping

from .state import ANALYSIS_STAGES, canonical_json


MAX_MANIFEST_FILES = 10_000
MAX_MANIFEST_BYTES = 256 * 1024 * 1024


def _is_reparse_or_link(path: Path) -> bool:
    stat = path.lstat()
    attributes = getattr(stat, "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & 0x400)


def _digest_file(path: Path) -> tuple[tuple[int, int, int, int], str]:
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        digest = hashlib.sha256()
        while chunk := stream.read(64 * 1024):
            digest.update(chunk)
        after = os.fstat(stream.fileno())
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_identity != after_identity:
        raise ValueError("source changed while reading")
    return before_identity, digest.hexdigest()


@dataclass(frozen=True)
class TargetSnapshot:
    root: str
    digest: str
    entries: dict[str, tuple[tuple[int, int, int, int], str]]

    @classmethod
    def capture(cls, root: str | Path) -> "TargetSnapshot":
        target = Path(root).resolve()
        if not target.is_dir() or _is_reparse_or_link(target):
            raise ValueError("target root is unavailable")
        entries: dict[str, tuple[tuple[int, int, int, int], str]] = {}
        total_bytes = 0
        for current, dirs, names in os.walk(target, followlinks=False):
            current_path = Path(current)
            dirs[:] = [name for name in dirs if name != ".git"]
            for name in sorted(names):
                source = current_path / name
                if _is_reparse_or_link(source):
                    raise ValueError("target contains symlink or reparse point")
                stat = source.lstat()
                if not os.path.isfile(source):
                    continue
                total_bytes += stat.st_size
                if len(entries) >= MAX_MANIFEST_FILES or total_bytes > MAX_MANIFEST_BYTES:
                    raise ValueError("target manifest exceeds declared bound")
                identity, content_hash = _digest_file(source)
                entries[source.relative_to(target).as_posix()] = (identity, content_hash)
        digest = hashlib.sha256(canonical_json(entries).encode("utf-8")).hexdigest()
        return cls(str(target), digest, entries)


class ObservationRegistry:
    """Own observations until finalization or process cleanup invalidates them."""

    def __init__(self, root: str | Path, binding: Mapping[str, Any]) -> None:
        self._root = Path(root).resolve()
        self._binding_id = str(binding["binding_id"])
        self._snapshot_digest = str(binding["target_snapshot_hash"])
        self._issued: dict[str, dict[str, Any]] = {}

    def _relative_regular_file(self, source: str | Path) -> tuple[Path, str]:
        candidate = Path(source)
        if not candidate.is_absolute():
            candidate = self._root / candidate
        candidate = candidate.absolute()
        try:
            relative = candidate.relative_to(self._root)
        except ValueError as exc:
            raise ValueError("path is outside target") from exc
        current = self._root
        if _is_reparse_or_link(current):
            raise ValueError("target root is unavailable")
        for component in relative.parts:
            current = current / component
            if _is_reparse_or_link(current):
                raise ValueError("source is symlink or reparse point")
        if not candidate.is_file():
            raise ValueError("source is not a regular file")
        return candidate, relative.as_posix()

    def _assert_snapshot(self, snapshot: TargetSnapshot) -> None:
        if snapshot.root != str(self._root) or snapshot.digest != self._snapshot_digest:
            raise ValueError("target snapshot changed")

    def issue_present(self, stage: str, source: str | Path, start_line: int, end_line: int, redacted_text: str) -> dict[str, str]:
        if stage not in ANALYSIS_STAGES:
            raise ValueError("invalid observation stage")
        self._assert_snapshot(TargetSnapshot.capture(self._root))
        path, relative = self._relative_regular_file(source)
        identity, content_hash = _digest_file(path)
        if not isinstance(redacted_text, str) or "[REDACTED]" not in redacted_text and ("password=" in redacted_text.lower() or "token=" in redacted_text.lower()):
            raise ValueError("unredacted observation text")
        canonical = {
            "location": relative,
            "range": f"{int(start_line)}-{int(end_line)}",
            "status": "confirmed",
            "content_fingerprint": hashlib.sha256(redacted_text.encode("utf-8")).hexdigest(),
            "redacted": True,
        }
        ref = "obs_" + secrets.token_urlsafe(18)
        self._issued[ref] = {
            "stage": stage,
            "snapshot_hash": self._snapshot_digest,
            "canonical_evidence": canonical,
            "source": relative,
            "identity": identity,
            "content_hash": content_hash,
        }
        return {"observation_ref": ref}

    def issue_absence(self, stage: str, scope: str, glob: str, pattern: str | None) -> dict[str, str]:
        if stage not in ANALYSIS_STAGES:
            raise ValueError("invalid observation stage")
        self._assert_snapshot(TargetSnapshot.capture(self._root))
        descriptor = {"scope": scope, "glob": glob, "pattern": pattern}
        ref = "obs_" + secrets.token_urlsafe(18)
        self._issued[ref] = {
            "stage": stage,
            "snapshot_hash": self._snapshot_digest,
            "canonical_evidence": {
                "location": f"search:{scope}", "range": "0-0", "status": "unknown",
                "content_fingerprint": hashlib.sha256(canonical_json(descriptor).encode("utf-8")).hexdigest(),
                "redacted": True,
            },
            "absence": descriptor,
        }
        return {"observation_ref": ref}

    def resolve(self, ref: str, stage: str, snapshot: TargetSnapshot) -> dict[str, Any]:
        if ref not in self._issued:
            raise ValueError("unknown observation reference")
        observation = self._issued[ref]
        if observation["stage"] != stage:
            raise ValueError("observation stage mismatch")
        self._assert_snapshot(snapshot)
        if "source" in observation:
            path, relative = self._relative_regular_file(observation["source"])
            identity, content_hash = _digest_file(path)
            if relative != observation["source"] or identity != observation["identity"] or content_hash != observation["content_hash"]:
                raise ValueError("observation source changed")
        return {
            "snapshot_hash": observation["snapshot_hash"],
            "canonical_evidence": dict(observation["canonical_evidence"]),
        }

    def invalidate_from(self, stage: str) -> None:
        boundary = ANALYSIS_STAGES.index(stage)
        self._issued = {
            ref: observation for ref, observation in self._issued.items()
            if ANALYSIS_STAGES.index(observation["stage"]) < boundary
        }

    def clear(self) -> None:
        self._issued.clear()
