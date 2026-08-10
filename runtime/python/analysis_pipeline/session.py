"""Process-private analysis lifecycle and safe local target binding."""
from __future__ import annotations

import secrets
import subprocess
from pathlib import Path
from typing import Any, Mapping

from .observations import ObservationRegistry, TargetSnapshot
from .stage_contracts import (
    client_payload_submission_template,
    promote_discovery_facts,
    promote_execution_facts,
    promote_relationship_facts,
    promote_boundary_facts,
    promote_contract_facts,
    project_discovery_handoff,
    project_execution_handoff,
    project_relationships_handoff,
    project_boundaries_handoff,
    project_contracts_handoff,
    project_predecessor_fact_statuses,
    required_report_slot_ids,
    validate_discovery_payload,
    validate_execution_payload,
    validate_relationships_payload,
    validate_boundaries_payload,
    validate_contracts_payload,
)
from .state import ANALYSIS_STAGES, PipelineState, create_state
from .report_projection import project_and_render
from .tools.survey import compute_survey


SKILL_BY_STAGE = {
    "discovery": "analyze-k8s-discovery",
    "execution": "analyze-k8s-execution",
    "relationships": "analyze-k8s-relationships",
    "boundaries": "analyze-k8s-boundaries",
    "contracts": "analyze-k8s-contracts",
    "finalize": "analyze-k8s-finalize",
}

# Precision-tool budget: one combined read_evidence/locate_evidence/
# list_target_paths call per stage, on top of the pushed survey.
PRECISION_CALL_LIMIT = 1
# Submit-retry budget: three corrected resubmissions before the fourth
# attempt is handled specially (see docs/superpowers/specs/
# 2026-08-09-bounded-stage-surveys-design.md, "Submit retries"). Only the
# counter and its budget-visibility field are wired up so far; the fourth-
# attempt server-side degradation itself is a separate follow-up.
SUBMIT_REJECTION_LIMIT = 3


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
        self.precision_calls_used = 0
        self.submit_rejections = 0

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

    def submit_discovery(self, payload: Any) -> dict[str, Any]:
        self.assert_active()
        if self.current_stage != "discovery":
            raise ValueError("stage_order")
        assert self.registry is not None
        assert self.snapshot is not None
        assert self.binding is not None
        assert self.pipeline is not None
        payload = validate_discovery_payload(payload, self.registry, self.snapshot, self.binding)
        next_pipeline = promote_discovery_facts(self.pipeline, payload)
        self.pipeline = next_pipeline
        self.current_stage = next_pipeline.current_stage
        self.revision = next_pipeline.revision
        self.transition_token = self._token()
        return self.handoff("discovery")

    def submit_execution(self, payload: Any) -> dict[str, Any]:
        self.assert_active()
        if self.current_stage != "execution":
            raise ValueError("stage_order")
        assert self.registry is not None
        assert self.snapshot is not None
        assert self.binding is not None
        assert self.pipeline is not None
        discovery_input = project_discovery_handoff(self.pipeline)
        payload = validate_execution_payload(
            payload,
            self.registry,
            self.snapshot,
            self.binding,
            discovery_input["discovery_fact_refs"],
            discovery_input["candidate_ids"],
            [fact["ref"] for fact in discovery_input["semantic_facts"]],
        )
        next_pipeline = promote_execution_facts(self.pipeline, payload)
        self.pipeline = next_pipeline
        self.current_stage = next_pipeline.current_stage
        self.revision = next_pipeline.revision
        self.transition_token = self._token()
        return self.handoff("execution")

    def submit_relationships(self, payload: Any) -> dict[str, Any]:
        self.assert_active()
        if self.current_stage != "relationships":
            raise ValueError("stage_order")
        assert self.registry is not None
        assert self.snapshot is not None
        assert self.binding is not None
        assert self.pipeline is not None
        discovery_input = project_discovery_handoff(self.pipeline)
        execution_input = project_execution_handoff(self.pipeline)
        payload = validate_relationships_payload(
            payload,
            self.registry,
            self.snapshot,
            self.binding,
            discovery_input["discovery_fact_refs"],
            execution_input["execution_fact_refs"],
            execution_input["process_ids"],
        )
        next_pipeline = promote_relationship_facts(self.pipeline, payload)
        self.pipeline = next_pipeline
        self.current_stage = next_pipeline.current_stage
        self.revision = next_pipeline.revision
        self.transition_token = self._token()
        return self.handoff("relationships")

    def submit_boundaries(self, payload: Any) -> dict[str, Any]:
        self.assert_active()
        if self.current_stage != "boundaries":
            raise ValueError("stage_order")
        assert self.registry is not None and self.snapshot is not None and self.binding is not None and self.pipeline is not None
        discovery = project_discovery_handoff(self.pipeline)
        execution = project_execution_handoff(self.pipeline)
        relationships = project_relationships_handoff(self.pipeline)
        payload = validate_boundaries_payload(payload, self.registry, self.snapshot, self.binding, discovery["discovery_fact_refs"], execution["execution_fact_refs"], relationships["relationship_fact_refs"], execution["process_ids"], discovery["candidate_ids"])
        self.pipeline = promote_boundary_facts(self.pipeline, payload)
        self.current_stage, self.revision, self.transition_token = self.pipeline.current_stage, self.pipeline.revision, self._token()
        return self.handoff("boundaries")

    def submit_contracts(self, payload: Any) -> dict[str, Any]:
        self.assert_active()
        if self.current_stage != "contracts":
            raise ValueError("stage_order")
        assert self.registry is not None and self.snapshot is not None and self.binding is not None and self.pipeline is not None and self.mode is not None
        discovery = project_discovery_handoff(self.pipeline)
        execution = project_execution_handoff(self.pipeline)
        relationships = project_relationships_handoff(self.pipeline)
        boundaries = project_boundaries_handoff(self.pipeline)
        payload = validate_contracts_payload(payload, self.registry, self.snapshot, self.binding, self.mode, discovery["discovery_fact_refs"], execution["execution_fact_refs"], relationships["relationship_fact_refs"], boundaries["boundaries_fact_refs"], project_predecessor_fact_statuses(self.pipeline))
        self.pipeline = promote_contract_facts(self.pipeline, payload)
        self.current_stage, self.revision, self.transition_token = self.pipeline.current_stage, self.pipeline.revision, self._token()
        return self.handoff("contracts")

    def finalize_and_render(self) -> dict[str, Any]:
        self.assert_active()
        if self.current_stage != "finalize":
            raise ValueError("stage_order")
        assert self.pipeline is not None and self.mode is not None and self.analysis_id is not None
        target_metadata = {
            "대상 유형": "local Git repository",
            "Repository URL 또는 Local path": self.target_subdirectory or ".",
            "접근 방식": "read-only static MCP",
            "확인된 저장소 루트": ".",
            "branch, tag 또는 commit": str(self.binding.get("git_revision", "unknown")) if self.binding else "unknown",
            "분석 경로": self.target_subdirectory or ".",
            "출력 모드": self.mode,
        }
        markdown = project_and_render(self.pipeline, self.mode, target_metadata)
        result = {
            "status": "finalized",
            "analysis_id": self.analysis_id,
            "mode": self.mode,
            "revision": self.revision,
            "markdown": markdown,
        }
        return result

    def handoff(self, completed_stage: str | None) -> dict[str, Any]:
        if not self.active or self.mode is None or self.transition_token is None or self.current_stage is None:
            raise ValueError("analysis_not_started")
        stage_input: dict[str, Any] = {"mode": self.mode}
        submission_template: dict[str, Any] | None = None
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
            stage_input["discovery_fact_refs"] = project_discovery_handoff(self.pipeline)["discovery_fact_refs"]
        elif self.current_stage == "boundaries":
            assert self.pipeline is not None
            accepted_output = project_relationships_handoff(self.pipeline)
            stage_input.update(accepted_output)
            stage_input["discovery_fact_refs"] = project_discovery_handoff(self.pipeline)["discovery_fact_refs"]
            stage_input["execution_fact_refs"] = project_execution_handoff(self.pipeline)["execution_fact_refs"]
            stage_input["candidate_ids"] = project_discovery_handoff(self.pipeline)["candidate_ids"]
            stage_input["process_ids"] = project_execution_handoff(self.pipeline)["process_ids"]
        elif self.current_stage == "contracts":
            assert self.pipeline is not None
            accepted_output = project_boundaries_handoff(self.pipeline)
            stage_input.update(accepted_output)
            stage_input["discovery_fact_refs"] = project_discovery_handoff(self.pipeline)["discovery_fact_refs"]
            stage_input["execution_fact_refs"] = project_execution_handoff(self.pipeline)["execution_fact_refs"]
            stage_input["relationship_fact_refs"] = project_relationships_handoff(self.pipeline)["relationship_fact_refs"]
            stage_input["required_report_slot_ids"] = required_report_slot_ids(self.mode)
            stage_input["fact_statuses"] = project_predecessor_fact_statuses(self.pipeline)
        elif self.current_stage == "finalize":
            assert self.pipeline is not None
            accepted_output = project_contracts_handoff(self.pipeline)
            stage_input.update(accepted_output)
        self.precision_calls_used = 0
        self.submit_rejections = 0
        if self.current_stage in ANALYSIS_STAGES:
            assert self.registry is not None and self.target_root is not None
            survey_kwargs: dict[str, Any] = {}
            if self.current_stage == "contracts":
                survey_kwargs = {
                    "required_report_slots": stage_input.get("required_report_slot_ids", []),
                    "fact_statuses": stage_input.get("fact_statuses", {}),
                }
            stage_input["survey"] = compute_survey(self.target_root, self.current_stage, self.registry, **survey_kwargs)
            submission_template = client_payload_submission_template(self.current_stage)
            stage_input["budget"] = {
                "precision_calls_remaining": PRECISION_CALL_LIMIT - self.precision_calls_used,
                "submit_rejections_remaining": SUBMIT_REJECTION_LIMIT - self.submit_rejections,
            }
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
            "submission_template": submission_template,
        }

    def clear(self) -> None:
        if self.registry is not None:
            self.registry.clear()
        self.__init__(self.command_directory, self.install_root)
