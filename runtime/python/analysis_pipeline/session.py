"""Process-private analysis lifecycle and safe local target binding."""
from __future__ import annotations

import secrets
import subprocess
from pathlib import Path
from typing import Any, Mapping

from .observations import ObservationRegistry, TargetSnapshot
from .stage_contracts import (
    promote_discovery_facts,
    promote_execution_facts,
    project_discovery_handoff,
    project_execution_handoff,
    validate_discovery_payload,
    validate_execution_payload,
)
from .state import ANALYSIS_STAGES, PipelineState, create_state


SKILL_BY_STAGE = {
    "discovery": "analyze-k8s-discovery",
    "execution": "analyze-k8s-execution",
    "relationships": "analyze-k8s-relationships",
    "boundaries": "analyze-k8s-boundaries",
    "contracts": "analyze-k8s-contracts",
    "finalize": "analyze-k8s-finalize",
}


class AnalysisSession:
    def __init__(self, command_directory: str | Path, install_root: str | Path | None = None) -> None:
        self.command_directory = Path(command_directory).resolve()
        self.install_root = Path(install_root or Path(__file__).resolve().parents[3]).resolve()
        self.analysis_id: str | None = None
        self.mode: str | None = None
        self.target_root: Path | None = None
        self.target_subdirectory: str | None = None
        self.snapshot: TargetSnapshot | None = None
        self.registry: ObservationRegistry | None = None
        self.binding: dict[str, Any] | None = None
        self.pipeline: PipelineState | None = None
        self.current_stage: str | None = None
        self.revision = 0
        self.transition_token: str | None = None

    @property
    def active(self) -> bool:
        return self.analysis_id is not None

    def _resolve_target(self, target_path: str) -> tuple[Path, Path]:
        supplied = Path(target_path)
        candidate = supplied if supplied.is_absolute() else self.command_directory / supplied
        candidate = candidate.resolve()
        if not candidate.is_dir():
            raise ValueError("target_not_directory")
        if candidate == self.install_root or self.install_root in candidate.parents:
            raise ValueError("target_is_skill_installation")
        if candidate.anchor == str(candidate):
            raise ValueError("target_unsafe_root")
        try:
            git_root_text = subprocess.run(
                ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ValueError("target_not_git_repository") from exc
        git_root = Path(git_root_text).resolve()
        try:
            candidate.relative_to(git_root)
        except ValueError as exc:
            raise ValueError("target_outside_git_root") from exc
        return candidate, git_root

    def _token(self) -> str:
        return "tr_" + secrets.token_urlsafe(18)

    def start(self, target_path: str, mode: str) -> dict[str, Any]:
        if self.active:
            raise ValueError("analysis_already_active")
        if not isinstance(target_path, str) or not target_path.strip():
            raise ValueError("target_path_required")
        if mode not in {"summary", "detailed"}:
            raise ValueError("invalid_mode")
        selected, git_root = self._resolve_target(target_path)
        snapshot = TargetSnapshot.capture(selected)
        revision = subprocess.run(
            ["git", "-C", str(git_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout.strip()
        binding = {
            "binding_id": "binding_" + secrets.token_urlsafe(12),
            "target_realpath": str(selected),
            "target_snapshot_hash": snapshot.digest,
            "git_root": str(git_root),
            "git_revision": revision,
            "skill_manifest_hash": "",
            "required_rule_ids": [],
        }
        self.analysis_id = "an_" + secrets.token_urlsafe(18)
        self.mode = mode
        self.target_root = selected
        self.target_subdirectory = selected.relative_to(git_root).as_posix() or "."
        self.snapshot = snapshot
        self.registry = ObservationRegistry(selected, binding)
        self.binding = binding
        self.pipeline = create_state(binding)
        self.current_stage = self.pipeline.current_stage
        self.revision = self.pipeline.revision
        self.transition_token = self._token()
        return self.handoff(None)

    def assert_active(self) -> None:
        if not self.active or self.target_root is None or self.registry is None or self.current_stage is None or self.snapshot is None or self.binding is None or self.pipeline is None:
            raise ValueError("analysis_not_started")
        if TargetSnapshot.capture(self.target_root).digest != self.snapshot.digest:
            raise ValueError("target_snapshot_changed")

    def assert_envelope(self, arguments: dict[str, Any]) -> None:
        self.assert_active()
        if arguments.get("analysis_id") != self.analysis_id:
            raise ValueError("analysis_not_found")
        if arguments.get("revision") != self.revision:
            raise ValueError("stale_revision")
        if arguments.get("transition_token") != self.transition_token:
            raise ValueError("stale_transition")

    def submit_discovery(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.assert_envelope(arguments)
        if self.current_stage != "discovery":
            raise ValueError("stage_order")
        assert self.registry is not None
        assert self.snapshot is not None
        assert self.binding is not None
        assert self.pipeline is not None
        payload = validate_discovery_payload(arguments.get("payload"), self.registry, self.snapshot, self.binding)
        next_pipeline = promote_discovery_facts(self.pipeline, payload)
        self.pipeline = next_pipeline
        self.current_stage = next_pipeline.current_stage
        self.revision = next_pipeline.revision
        self.transition_token = self._token()
        return self.handoff("discovery")

    def submit_execution(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.assert_envelope(arguments)
        if self.current_stage != "execution":
            raise ValueError("stage_order")
        assert self.registry is not None
        assert self.snapshot is not None
        assert self.binding is not None
        assert self.pipeline is not None
        discovery_input = project_discovery_handoff(self.pipeline)
        payload = validate_execution_payload(
            arguments.get("payload"),
            self.registry,
            self.snapshot,
            self.binding,
            discovery_input["discovery_fact_refs"],
        )
        next_pipeline = promote_execution_facts(self.pipeline, payload)
        self.pipeline = next_pipeline
        self.current_stage = next_pipeline.current_stage
        self.revision = next_pipeline.revision
        self.transition_token = self._token()
        return self.handoff("execution")

    def handoff(self, completed_stage: str | None) -> dict[str, Any]:
        if not self.active or self.mode is None or self.transition_token is None or self.current_stage is None:
            raise ValueError("analysis_not_started")
        stage_input: dict[str, Any] = {"mode": self.mode}
        accepted_output: dict[str, Any] = {}
        if self.current_stage == "discovery":
            stage_input.update({"accepted_fact_refs": [], "unknown_ids": [], "candidate_ids": []})
        elif self.current_stage == "execution":
            assert self.pipeline is not None
            accepted_output = project_discovery_handoff(self.pipeline)
            stage_input.update(accepted_output)
        elif self.current_stage == "relationships":
            assert self.pipeline is not None
            accepted_output = project_execution_handoff(self.pipeline)
            stage_input.update(accepted_output)
        return {
            "status": "accepted",
            "analysis_id": self.analysis_id,
            "mode": self.mode,
            "completed_stage": completed_stage,
            "revision": self.revision,
            "transition_token": self.transition_token,
            "next_skill": SKILL_BY_STAGE[self.current_stage],
            "accepted_output": accepted_output,
            "stage_input": stage_input,
        }

    def clear(self) -> None:
        if self.registry is not None:
            self.registry.clear()
        self.__init__(self.command_directory, self.install_root)
