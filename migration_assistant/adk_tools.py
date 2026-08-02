"""Google ADK function tools backed by the read-only RepositoryTools boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from google.adk.models import LlmResponse
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from .adk_function_tool import RepositoryFunctionTool
from .provenance import ObservationProvenance
from .repository_tools import _MAX_LINE_EVIDENCE_LINES, RepositoryToolError, RepositoryTools, redact_sensitive_value
from .target import BudgetExceededError
from .tool_protocol import RunControlLedger, RunPhase, ToolErrorCode, ToolIssue, error_envelope, success_envelope


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InspectTargetArgs(ToolArgs):
    pass


class ListTreeArgs(ToolArgs):
    relative: str = Field(default=".", description="Repository-relative directory; absolute paths, .., .git, and excluded observation scopes are forbidden.")
    max_depth: int | None = Field(default=None, ge=0, description="Optional non-negative traversal depth from relative.")


class FindFilesArgs(ToolArgs):
    pattern: str = Field(min_length=1, description="Repository-relative Python glob such as **/pom.xml; this is not a regular expression.")


class SearchTextArgs(ToolArgs):
    pattern: str = Field(min_length=1, description="Python regular expression matched against bounded UTF-8 text lines.")
    relative: str = Field(default=".", description="Repository-relative directory scope; absolute paths, .., .git, and excluded observation scopes are forbidden.")


class ReadFileArgs(ToolArgs):
    relative: str = Field(min_length=1, description="Repository-relative file path; absolute paths, .., .git, and excluded observation scopes are forbidden.")


class ReadFileLinesArgs(ToolArgs):
    relative: str = Field(min_length=1, description="Repository-relative file path previously confirmed by a Tool observation.")
    line_start: int = Field(ge=1, description="First 1-based line to read.")
    line_end: int = Field(ge=1, description="Inclusive 1-based end line; at most ten lines are returned.")

    @field_validator("line_end")
    @classmethod
    def validate_line_end(cls, value: int, info: ValidationInfo) -> int:
        line_start = info.data.get("line_start")
        if isinstance(line_start, int) and value < line_start:
            raise ValueError("line_end must be greater than or equal to line_start")
        if isinstance(line_start, int) and value - line_start + 1 > _MAX_LINE_EVIDENCE_LINES:
            raise ValueError("line range must contain at most ten lines")
        return value


class InspectGitMetadataArgs(ToolArgs):
    pass


EvidenceState = Literal["confirmed", "inferred", "unresolved", "conflicting"]


class ValidateEvidenceInput(ToolArgs):
    id: str | None = Field(default=None, description="Unique Evidence ID used by Finding.evidence_ids.")
    status: EvidenceState = Field(description="Exact evidence state; never use found, present, or absence.")
    path: str | None = Field(default=None, description="Repository-relative path for positive evidence.")
    line_start: int | None = Field(default=None, ge=1, description="First verified 1-based source line for positive evidence.")
    line_end: int | None = Field(default=None, ge=1, description="Last verified 1-based source line for positive evidence.")
    claim: str | None = Field(default=None, description="Specific repository fact supported by this Evidence.")
    text: str | None = Field(default=None, description="Exact redacted repository excerpt; use either text or excerpt.")
    excerpt: str | None = Field(default=None, description="Exact redacted repository excerpt; use either excerpt or text.")
    absence_scope: str | None = Field(default=None, description="Actual repository-relative search scope for unresolved absence evidence.")
    absence_pattern: str | None = Field(default=None, description="Actual search pattern used for unresolved absence evidence.")
    result: str | None = Field(default=None, description="Observed result of the unresolved search.")


class ValidateFindingInput(ToolArgs):
    id: str | None = Field(default=None, description="Unique Finding ID.")
    status: EvidenceState = Field(description="Exact finding state matching the evidence classification.")
    claim: str = Field(min_length=1, description="Migration-relevant claim or unresolved decision.")
    summary: str | None = Field(default=None, description="Optional concise elaboration of the claim.")
    evidence_ids: list[str] = Field(default_factory=list, description="IDs of positive Evidence supporting this Finding.")
    resolution_owner: Literal["repository", "user", "deployment_environment", "external_system"] | None = Field(default=None, description="Owner that can resolve an unresolved Finding.")
    resolution_source: str | None = Field(default=None, description="Source to consult for an unresolved Finding.")
    reason: str | None = Field(default=None, description="Why repository evidence cannot resolve this Finding.")


ComponentClassification = Literal[
    "배포 대상 후보",
    "저장소에 정의된 런타임 의존성",
    "외부 런타임 의존성",
    "배포 대상 후보에서 제외한 항목",
]


class ValidateFieldValueInput(ToolArgs):
    status: EvidenceState = Field(description="Exact state of this design input.")
    value: str | int | None = Field(default=None, description="Confirmed value; omit for unresolved.")
    evidence_ids: list[str] = Field(default_factory=list, description="IDs of Evidence proving this value; required unless unresolved.")
    absence_scope: str | None = Field(default=None, description="Actual repository-relative search scope; required for unresolved.")
    absence_pattern: str | None = Field(default=None, description="Actual search pattern used; required for unresolved.")
    result: str | None = Field(default=None, description="Observed result of the unresolved search.")


class ValidatePortInput(ToolArgs):
    container_port: ValidateFieldValueInput = Field(description="Port the component listens on inside the container.")
    name: ValidateFieldValueInput | None = Field(default=None, description="Optional port name.")
    protocol: ValidateFieldValueInput | None = Field(default=None, description="TCP or UDP when the repository states it.")
    purpose: ValidateFieldValueInput | None = Field(default=None, description="http, management, metrics, or unknown.")


class ValidateCommandsInput(ToolArgs):
    dependency_install: ValidateFieldValueInput | None = Field(default=None, description="Dependency installation only; never a build or a start command.")
    application_build: ValidateFieldValueInput | None = Field(default=None, description="Application build only; docker build is not an application build.")
    image_build: ValidateFieldValueInput | None = Field(default=None, description="Container image build only.")
    production_startup: ValidateFieldValueInput | None = Field(default=None, description="Production start command only; a development server is not production startup.")


class ValidateContainerImageInput(ToolArgs):
    reference: ValidateFieldValueInput | None = Field(default=None, description="Image reference stated by the repository; unresolved when none exists.")


class ValidateComponentInput(ToolArgs):
    name: ValidateFieldValueInput = Field(description="Component name grounded in repository evidence.")
    classification: ValidateFieldValueInput = Field(description="One of the four migration buckets; only 배포 대상 후보 receives manifests.")
    runtime: ValidateFieldValueInput | None = Field(default=None, description="Runtime the repository states.")
    commands: ValidateCommandsInput | None = Field(default=None, description="Four execution stages kept apart.")
    ports: list[ValidatePortInput] = Field(default_factory=list, description="Ports evidenced by the repository.")
    container_image: ValidateContainerImageInput | None = Field(default=None, description="Container image facts.")


class ValidateAnalysisArgs(ToolArgs):
    status: Literal["complete", "partial", "failed"] = Field(description="Top-level outcome; Evidence states are not valid here.")
    summary: str = Field(min_length=1, description="Korean evidence-grounded analysis summary.")
    evidence: list[ValidateEvidenceInput] = Field(description="Complete Evidence Ledger candidate.")
    findings: list[ValidateFindingInput] = Field(description="Complete structured Finding candidate linked to Evidence IDs.")
    iterations: int = Field(ge=0, description="Observed Agent iteration count.")
    errors: list[str] = Field(description="Non-empty only for partial or failed outcomes; do not put unresolved deployment choices here.")
    termination: str = Field(default="normal", description="Termination reason, normally normal.")
    components: list[ValidateComponentInput] = Field(default_factory=list, description="Deployment units and runtime dependencies found in the repository, each field carrying its own Evidence or a scoped absence.")


TOOL_DESCRIPTIONS = {
    "inspect_target": """Use when: starting a run and confirming the local Git/read-only safety boundary.\nDo not use when: collecting application facts or line-backed Evidence.\nArguments: none.\nReturns: repository safety metadata, not application Evidence.\nLimits: consumes exploration budget and never reads application files.\nOn error: stop if the target is not a safe local Git Repository.\nNext action: call list_tree, find_files, or search_text only after a successful inspection.""",
    "list_tree": """Use when: discovering bounded Repository-relative structure and likely component boundaries.\nDo not use when: proving file content, reading .git, or treating path names as application Evidence.\nArguments: relative is a safe Repository-relative directory; max_depth is an optional non-negative depth.\nReturns: an entries list plus scope metadata; scope_limited=true means observation exclusions hid one or more entries. Exclusion metadata is not application Evidence.\nLimits: excludes AGENTS.md, SKILL.md, CONTEXT.md, README.md, dependency/build output, virtual environments, .dryforge, and .git; excluded content is never returned.\nOn error: correct only the reported field; never retry a forbidden path.\nNext action: select a concrete candidate for find_files, search_text, or read_file.""",
    "find_files": """Use when: locating file candidates by a known Repository-relative glob such as **/pom.xml.\nDo not use when: searching source text; pattern is a Python glob, not a regular expression.\nArguments: pattern is a non-empty Repository-relative glob without absolute paths, .., or .git.\nReturns: a matches list plus scope metadata; scope_limited=true means exclusions hid matching candidates. Exclusion metadata is not application Evidence.\nLimits: excludes AGENTS.md, SKILL.md, CONTEXT.md, README.md, dependency/build output, virtual environments, .dryforge, and .git; excluded content is never returned.\nOn error: correct an invalid glob/path once; never retry forbidden scope.\nNext action: read a candidate or use search_text for a content claim.""",
    "search_text": """Use when: finding line-backed source, build, runtime, dependency, port, or environment evidence.\nDo not use when: locating names with glob syntax, reading binary data, or searching excluded instruction/.git scopes.\nArguments: pattern is a bounded Python regular expression; relative is a safe Repository-relative directory.\nReturns: bounded redacted hits with path, 1-based line, text, truncation metadata, and scope metadata. scope_limited=true or excluded_match_count>0 means the result cannot establish repository-wide absence; excluded matches never become hits or Evidence.\nLimits: excludes AGENTS.md, SKILL.md, CONTEXT.md, README.md, dependency/build output, virtual environments, .dryforge, and .git; excluded content is never returned. Results may be truncated and Secret values stay redacted.\nOn error: repair only an invalid/too-complex regex or choose a different safe scope; never retry a forbidden path.\nNext action: call read_file_lines on a confirmed hit before citing it as Evidence.""",
    "read_file": """Use when: understanding a known source/build/config file before selecting exact evidence lines.\nDo not use when: requesting directories, .git, AGENTS.md, SKILL.md, CONTEXT.md, README.md, dependency/build output, virtual environments, .dryforge, or executing code.\nArguments: relative is one safe Repository-relative file path.\nReturns: bounded redacted text or binary metadata as an untrusted observation.\nLimits: file-size and response budgets apply; whole-file text is not line-backed Evidence.\nOn error: use find_files/list_tree for not_found; never retry forbidden or budget-exhausted paths.\nNext action: use search_text or read_file_lines for exact Evidence.""",
    "read_file_lines": """Use when: copying an exact short excerpt from a path and line already confirmed by search_text or read_file.\nDo not use when: guessing line numbers, reading binaries/directories, or requesting .git, AGENTS.md, SKILL.md, CONTEXT.md, README.md, dependency/build output, virtual environments, or .dryforge.\nArguments: relative is Repository-relative; line_start and line_end are inclusive 1-based lines.\nReturns: at most ten redacted line observations with exact path and line metadata.\nLimits: the requested range must exist and target code is never executed.\nOn error: correct only the reported range/path once; never repeat forbidden or identical calls.\nNext action: copy the exact excerpt into Evidence, continue a different observation, or call validate_analysis.""",
    "inspect_git_metadata": """Use when: branch, HEAD, clean/dirty status, or remote metadata is relevant to repository context.\nDo not use when: reading .git files or using Git metadata as application behavior Evidence.\nArguments: none.\nReturns: restricted redacted Git command observations.\nLimits: never exposes .git contents and consumes exploration budget.\nOn error: do not inspect .git directly.\nNext action: continue application observation or call validate_analysis.""",
    "validate_analysis": """Use when: submitting the complete AnalysisResult candidate after collecting exact line-backed Evidence.\nDo not use when: sending a fragment, prose, a top-level Evidence status, guessed IDs/links, or ungrounded excerpts.\nArguments: status is complete|partial|failed; evidence uses confirmed|inferred|unresolved|conflicting; positive Evidence needs id/path/1-based lines/claim/exact excerpt, unresolved Evidence needs absence_scope/absence_pattern/result; Findings need unique IDs and positive evidence links or unresolved resolution metadata. components is the migration design input: one entry per deployment unit or runtime dependency, classified as 배포 대상 후보, 저장소에 정의된 런타임 의존성, 외부 런타임 의존성, or 배포 대상 후보에서 제외한 항목; every component field carries its own evidence_ids or an unresolved absence_scope/absence_pattern/result; keep dependency_install, application_build, image_build and production_startup apart.\nReturns: one envelope; ok=true with meta.terminal=true only when the repository-grounded candidate is accepted.\nLimits: complete needs no errors and at least one positive Finding linked to line-backed Evidence; partial needs errors and positive line-backed Evidence.\nOn error: preserve the candidate, fix the reported JSON field or apply an exact evidence correction, then resubmit the full candidate.\nNext action: only validate_analysis is appropriate for candidate_schema/evidence_grounding repair; after terminal success return the accepted structured result.""",
}


@dataclass
class DuplicateTracker:
    signatures: set[str] = field(default_factory=set)
    consecutive_no_progress: int = 0
    max_no_progress: int = 3

    @staticmethod
    def signature(tool_name: str, args: Mapping[str, object]) -> str:
        return json.dumps([tool_name, dict(args)], sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def begin(self, tool_name: str, args: Mapping[str, object]) -> dict[str, object] | None:
        signature = self.signature(tool_name, args)
        if signature in self.signatures:
            self.consecutive_no_progress += 1
            return {
                "tool_name": tool_name,
                "normalized_args": redact_sensitive_value(dict(args)),
                "valid": False,
                "duplicate": True,
                "no_progress": self.consecutive_no_progress,
                "error": "동일 Tool과 args 호출이 차단되었습니다. 이 호출을 반복하지 말고 다른 탐색 행동 또는 최종 분석을 선택하세요.",
            }
        self.signatures.add(signature)
        self.consecutive_no_progress = 0
        return None


@dataclass
class ValidationLedger:
    result: Any | None = None
    validation_error: str | None = None
    budget_exhausted: str | None = None
    tool_error: str | None = None
    observations: list[dict[str, object]] = field(default_factory=list)


class AdkRepositoryToolset:
    """Expose exactly eight functions to one ADK Agent."""

    def __init__(
        self,
        repository_tools: RepositoryTools,
        ledger: ValidationLedger,
        tracker: DuplicateTracker,
        *,
        control: RunControlLedger | None = None,
        provenance: ObservationProvenance | None = None,
    ) -> None:
        self.repository_tools = repository_tools
        self.ledger = ledger
        self.tracker = tracker
        self.control = control or RunControlLedger()
        self.provenance = provenance or ObservationProvenance()
        definitions = (
            ("inspect_target", InspectTargetArgs, lambda value: self.inspect_target()),
            ("list_tree", ListTreeArgs, lambda value: self.list_tree(**value.model_dump())),
            ("find_files", FindFilesArgs, lambda value: self.find_files(**value.model_dump())),
            ("search_text", SearchTextArgs, lambda value: self.search_text(**value.model_dump())),
            ("read_file", ReadFileArgs, lambda value: self.read_file(**value.model_dump())),
            ("read_file_lines", ReadFileLinesArgs, lambda value: self.read_file_lines(**value.model_dump())),
            ("inspect_git_metadata", InspectGitMetadataArgs, lambda value: self.inspect_git_metadata()),
            ("validate_analysis", ValidateAnalysisArgs, lambda value: self.validate_analysis(**value.model_dump(mode="json"))),
        )
        self._tools = tuple(
            RepositoryFunctionTool(
                name=name,
                description=TOOL_DESCRIPTIONS[name],
                input_model=input_model,
                handler=handler,
                validation_error_code=(
                    ToolErrorCode.CANDIDATE_SCHEMA
                    if name == "validate_analysis"
                    else ToolErrorCode.INVALID_ARGUMENTS
                ),
                invalid_argument_actions=(name,),
            )
            for name, input_model, handler in definitions
        )
        self._tools_by_name = {tool.name: tool for tool in self._tools}

    @staticmethod
    def _canonical_tool_name(raw_name: str) -> str | None:
        candidates: set[str] = set()
        compact_raw = raw_name.replace("_", "")
        suffixes = ("arg", "args", "argument", "arguments")
        for public_name in TOOL_DESCRIPTIONS:
            compact_public = public_name.replace("_", "")
            if raw_name == public_name or compact_raw == compact_public:
                candidates.add(public_name)
                continue
            if any(
                raw_name == public_name + suffix
                or compact_raw == compact_public + suffix
                for suffix in suffixes
            ):
                candidates.add(public_name)
        return next(iter(candidates)) if len(candidates) == 1 else None

    @staticmethod
    def _protocol_response(issue: ToolIssue) -> LlmResponse:
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text="Tool protocol 검증에 실패했습니다.")],
            ),
            custom_metadata={"protocol_issue": error_envelope(issue)["error"]},
            partial=False,
        )

    @staticmethod
    def _issue_from_metadata(value: object) -> ToolIssue | None:
        if not isinstance(value, Mapping):
            return None
        try:
            code = ToolErrorCode(str(value.get("code")))
        except ValueError:
            return None
        return ToolIssue(
            code=code,
            category=str(value.get("category") or "protocol"),
            message=str(redact_sensitive_value(str(value.get("message") or "Tool protocol 검증에 실패했습니다."))),
            field_path=str(value["field_path"]) if value.get("field_path") is not None else None,
            retryable=value.get("retryable") is True,
        )

    def after_model_callback(self, callback_context: object, llm_response: LlmResponse) -> LlmResponse | None:
        """Reject malformed, unknown, or schema-invalid calls before ADK dispatch."""

        metadata = llm_response.custom_metadata or {}
        adapter_issue = self._issue_from_metadata(metadata.get("protocol_issue"))
        if adapter_issue is not None:
            self.control.record_issue(
                adapter_issue,
                allowed_next_actions=tuple(self._tools_by_name),
            )
            return llm_response

        content = llm_response.content
        if content is None:
            return None
        canonicalized: list[dict[str, str]] = []
        for part in content.parts or []:
            call = part.function_call
            if call is None:
                continue
            original_name = call.name or ""
            canonical_name = self._canonical_tool_name(original_name)
            if canonical_name is None:
                issue = ToolIssue(
                    code=ToolErrorCode.INVALID_TOOL_NAME,
                    category="protocol",
                    message="등록된 공개 Tool allowlist에 없는 이름입니다.",
                    field_path="$.name",
                    retryable=True,
                )
                self.control.record_issue(issue, allowed_next_actions=tuple(self._tools_by_name))
                return self._protocol_response(issue)
            tool = self._tools_by_name[canonical_name]
            issue = tool.argument_issue(dict(call.args or {}))
            if issue is not None:
                self.control.record_issue(issue, allowed_next_actions=(canonical_name,))
                return self._protocol_response(issue)
            if canonical_name != original_name:
                call.name = canonical_name
                canonicalized.append({"original": original_name, "canonical": canonical_name})

        self.control.protocol_issue = None
        self.control.next_actions = None
        if canonicalized:
            llm_response.custom_metadata = {**metadata, "canonicalized_calls": canonicalized}
        return llm_response

    def _phase_actions(self) -> tuple[str, ...]:
        names = tuple(self._tools_by_name)
        if self.control.phase == RunPhase.INIT:
            return ("inspect_target",)
        if self.control.phase == RunPhase.VALIDATE:
            return ("validate_analysis",)
        if self.control.phase == RunPhase.REPAIR:
            return self.control.allowed_next_actions(names)
        if self.control.phase in {RunPhase.DONE, RunPhase.PARTIAL_OR_FAILED}:
            return ()
        return tuple(name for name in names if name != "inspect_target")

    def before_tool_callback(self, tool: object, args: dict[str, Any], tool_context: object) -> dict[str, Any] | None:
        """Enforce run phase, blocked signatures, and exploration budget before execution."""

        name = str(getattr(tool, "name", ""))
        allowed = self._phase_actions()
        declared_tool = self._tools_by_name.get(name)
        if declared_tool is None:
            issue = ToolIssue(
                code=ToolErrorCode.INVALID_TOOL_NAME,
                category="protocol",
                message="등록된 공개 Tool allowlist에 없는 이름입니다.",
                field_path="$.name",
                retryable=True,
            )
            self.control.record_issue(issue, allowed_next_actions=allowed)
            return error_envelope(issue, allowed_next_actions=allowed)
        argument_issue = declared_tool.argument_issue(args)
        if argument_issue is not None:
            self.control.record_issue(argument_issue, allowed_next_actions=(name,))
            return error_envelope(argument_issue, allowed_next_actions=(name,))
        signature = self.tracker.signature(name, declared_tool.normalized_args(args))
        if signature in self.control.blocked_signatures:
            issue = ToolIssue(
                code=ToolErrorCode.DUPLICATE_CALL,
                category="progress",
                message="이전에 차단된 동일 Tool 호출은 다시 실행할 수 없습니다.",
                retryable=False,
            )
            self.control.record_issue(
                issue,
                blocked_signature=signature,
                allowed_next_actions=allowed,
            )
            return error_envelope(issue, allowed_next_actions=allowed)
        if name not in allowed:
            issue = ToolIssue(
                code=ToolErrorCode.INVALID_ARGUMENTS,
                category="state",
                message=f"Tool {name}은 현재 phase={self.control.phase.value}에서 호출할 수 없습니다.",
                field_path="$.name",
                retryable=True,
            )
            self.control.record_issue(issue, allowed_next_actions=allowed)
            return error_envelope(issue, allowed_next_actions=allowed)
        budget = self.repository_tools.budget
        if name != "validate_analysis" and budget.explorations >= budget.max_explorations:
            issue = ToolIssue(
                code=ToolErrorCode.BUDGET_EXHAUSTED,
                category="resource",
                message="Repository exploration budget이 소진되었습니다.",
                retryable=False,
            )
            self.control.record_issue(issue, allowed_next_actions=("validate_analysis",))
            return error_envelope(issue, allowed_next_actions=("validate_analysis",))
        return None

    def on_tool_error_callback(
        self,
        tool: object,
        args: dict[str, Any],
        tool_context: object,
        error: Exception,
    ) -> dict[str, Any]:
        """Convert ADK binding and unexpected execution errors to the public envelope."""

        name = str(getattr(tool, "name", ""))
        issue = ToolIssue(
            code=ToolErrorCode.INVALID_ARGUMENTS,
            category="execution",
            message=str(redact_sensitive_value(str(error))),
            retryable=isinstance(error, (TypeError, ValueError)),
        )
        actions = (name,) if issue.retryable and name in self._tools_by_name else ("validate_analysis",)
        self.control.record_issue(issue, allowed_next_actions=actions)
        return error_envelope(
            issue,
            allowed_next_actions=actions,
        )

    def _record_provenance(self, name: str, result: object) -> None:
        """Record observed line coordinates for measurement; never affects validation."""

        if name in ("search_text", "read_file_lines"):
            items = result.get("hits") if isinstance(result, Mapping) else result
            if name == "search_text" and isinstance(items, list):
                self.provenance.record_search(len(items))
            if not isinstance(items, list):
                return
            for item in items:
                if not isinstance(item, Mapping):
                    continue
                path = item.get("path")
                start = item.get("line_start")
                end = item.get("line_end")
                if isinstance(path, str) and isinstance(start, int) and isinstance(end, int):
                    self.provenance.record(name, path, start, end)
            return
        if name != "read_file" or not isinstance(result, Mapping) or result.get("binary"):
            return
        text = result.get("text")
        path = result.get("path")
        if not isinstance(text, str) or not isinstance(path, str):
            return
        lines = text.splitlines()
        # The byte prefix can cut the final line in half, and a half line was never
        # fully observed. Dropping it can only under-count, never over-claim.
        if result.get("truncated") and lines:
            lines = lines[:-1]
        if lines:
            self.provenance.record("read_file", path, 1, len(lines))

    def _call(self, name: str, args: Mapping[str, object], operation: Any) -> object:
        signature = self.tracker.signature(name, args)
        duplicate = self.tracker.begin(name, args)
        if duplicate is not None:
            issue = ToolIssue(
                code=ToolErrorCode.DUPLICATE_CALL,
                category="progress",
                message=str(duplicate["error"]),
                retryable=False,
            )
            self.control.record_issue(
                issue,
                blocked_signature=signature,
                allowed_next_actions=("validate_analysis",),
            )
            return error_envelope(
                issue,
                allowed_next_actions=("validate_analysis",),
                meta={"no_progress": duplicate["no_progress"]},
            )
        try:
            result = operation()
            if name == "search_text" and isinstance(result, Mapping):
                hits = result.get("hits")
                if isinstance(hits, list):
                    self.ledger.observations.extend(redact_sensitive_value(item) for item in hits if isinstance(item, Mapping) and item.get("path"))
            elif name == "read_file_lines" and isinstance(result, list):
                self.ledger.observations.extend(redact_sensitive_value(item) for item in result if isinstance(item, Mapping) and item.get("path"))
            if len(self.ledger.observations) > 64:
                del self.ledger.observations[:-64]
            self._record_provenance(name, result)
            if name == "inspect_target":
                self.control.phase = RunPhase.DISCOVER
            elif name == "validate_analysis":
                self.control.phase = RunPhase.VALIDATE
            else:
                self.control.phase = RunPhase.GROUND
            return success_envelope(redact_sensitive_value(result))
        except (BudgetExceededError, RepositoryToolError, TypeError, ValueError) as error:
            safe_error = str(redact_sensitive_value(str(error)))
            if isinstance(error, BudgetExceededError):
                self.ledger.budget_exhausted = safe_error
                issue = ToolIssue(
                    code=ToolErrorCode.BUDGET_EXHAUSTED,
                    category="resource",
                    message=safe_error,
                    retryable=False,
                )
                actions = ("validate_analysis",)
            elif isinstance(error, RepositoryToolError):
                self.ledger.tool_error = safe_error
                issue = ToolIssue(
                    code=error.issue.code,
                    category=error.issue.category,
                    message=safe_error,
                    field_path=error.issue.field_path,
                    retryable=error.issue.retryable,
                )
                actions = error.allowed_next_actions
            else:
                self.ledger.tool_error = safe_error
                issue = ToolIssue(
                    code=ToolErrorCode.INVALID_ARGUMENTS,
                    category="validation",
                    message=safe_error,
                    retryable=True,
                )
                actions = (name, "validate_analysis")
            self.control.record_issue(
                issue,
                blocked_signature=(
                    signature
                    if issue.code in {ToolErrorCode.FORBIDDEN_PATH, ToolErrorCode.DUPLICATE_CALL}
                    else None
                ),
                allowed_next_actions=actions,
            )
            return error_envelope(issue, allowed_next_actions=actions)

    def inspect_target(self) -> dict[str, object]:
        """Inspect the local Git Repository safety boundary. This is not application evidence."""
        return self._call("inspect_target", {}, self.repository_tools.inspect_target)  # type: ignore[return-value]

    def list_tree(self, relative: str = ".", max_depth: int | None = None) -> object:
        """List Repository-relative files and disclose whether exclusions limited the scope."""
        return self._call("list_tree", {"relative": relative, "max_depth": max_depth}, lambda: self.repository_tools.list_tree(relative, max_depth))

    def find_files(self, pattern: str) -> object:
        """Find bounded Repository-relative file candidates and disclose excluded matches."""
        return self._call("find_files", {"pattern": pattern}, lambda: self.repository_tools.find_files(pattern))

    def search_text(self, pattern: str, relative: str = ".") -> object:
        """Search bounded text hits while disclosing whether exclusions limited the scope."""
        return self._call("search_text", {"pattern": pattern, "relative": relative}, lambda: self.repository_tools.search_text(pattern, relative))

    def read_file(self, relative: str) -> object:
        """Read one bounded Repository-relative file; .git internals are forbidden and code is never executed."""
        return self._call("read_file", {"relative": relative}, lambda: self.repository_tools.read_file(relative))

    def read_file_lines(self, relative: str, line_start: int, line_end: int) -> object:
        """Read at most ten lines of line-backed evidence; .git internals are forbidden and the range must exist."""
        args = {"relative": relative, "line_start": line_start, "line_end": line_end}
        return self._call("read_file_lines", args, lambda: self.repository_tools.read_file_lines(relative, line_start, line_end))

    def inspect_git_metadata(self) -> object:
        """Read restricted Git metadata only; never read .git files."""
        return self._call("inspect_git_metadata", {}, self.repository_tools.inspect_git_metadata)

    def validate_analysis(
        self,
        status: Literal["complete", "partial", "failed"],
        summary: str,
        evidence: list[dict],
        findings: list[dict],
        iterations: int,
        errors: list[str],
        termination: str = "normal",
        components: list[dict] | None = None,
    ) -> dict[str, object]:
        """Validate the full candidate before termination.

        Pass the complete candidate with these required fields. Each evidence item
        must contain status; positive items require repository-relative path,
        line_start and line_end. Unresolved items require absence_scope,
        absence_pattern and result. Extra fields are rejected by Pydantic. A
        partial candidate must include a non-empty errors list describing the
        genuine unresolved repository ambiguity; an empty list is invalid.
        """
        candidate = redact_sensitive_value({
            "status": status,
            "summary": summary,
            "evidence": evidence,
            "findings": findings,
            "iterations": iterations,
            "errors": errors,
            "termination": termination,
            "components": components or [],
        })
        if self.control.candidate_repeated(candidate):
            issue = ToolIssue(
                code=ToolErrorCode.DUPLICATE_CALL,
                category="progress",
                message="동일한 AnalysisResult candidate가 변경 없이 반복 제출되었습니다.",
                field_path="$",
                retryable=False,
            )
            self.ledger.validation_error = issue.message
            self.control.record_issue(issue, allowed_next_actions=())
            return error_envelope(issue, allowed_next_actions=())
        execution = self._call("validate_analysis", candidate, lambda: self.repository_tools.validate_analysis(candidate))
        if not isinstance(execution, Mapping) or execution.get("ok") is not True:
            return dict(execution) if isinstance(execution, Mapping) else error_envelope(
                ToolIssue(
                    code=ToolErrorCode.CANDIDATE_SCHEMA,
                    category="validation",
                    message="validate_analysis가 protocol envelope을 반환하지 않았습니다.",
                    retryable=True,
                ),
                allowed_next_actions=("validate_analysis",),
            )
        preliminary = execution.get("data")
        corrections = preliminary.get("evidence_corrections") if isinstance(preliminary, Mapping) else []
        if not isinstance(preliminary, Mapping) or preliminary.get("valid") is not True:
            response = dict(preliminary) if isinstance(preliminary, Mapping) else {"valid": False, "errors": ["검증 응답 형식이 올바르지 않습니다."]}
            details = response.get("errors")
            if isinstance(details, list) and details:
                safe_details = "; ".join(str(redact_sensitive_value(item)) for item in details[:8])
                self.ledger.validation_error = f"Repository evidence 검증에 실패했습니다: {safe_details}"
            else:
                self.ledger.validation_error = "Repository evidence 검증에 실패했습니다."
            grounding = bool(corrections)
            typed_issues = response.get("issues", [])
            if isinstance(typed_issues, list) and any(
                isinstance(issue, Mapping)
                and issue.get("code") in {"absence_contradicted", "absence_unverified"}
                for issue in typed_issues
            ):
                grounding = True
            issue = ToolIssue(
                code=(ToolErrorCode.EVIDENCE_GROUNDING if grounding else ToolErrorCode.CANDIDATE_SCHEMA),
                category=("grounding" if grounding else "validation"),
                message=self.ledger.validation_error,
                retryable=True,
            )
            self.control.record_issue(issue, allowed_next_actions=("validate_analysis",))
            return error_envelope(
                issue,
                allowed_next_actions=("validate_analysis",),
                meta={
                    "issues": typed_issues if isinstance(typed_issues, list) else [],
                    "validation_errors": response.get("errors", []),
                    "evidence_corrections": corrections if isinstance(corrections, list) else [],
                    "absence_corrections": response.get("absence_corrections", []),
                },
            )
        from .analysis import AnalysisResult, PydanticDependencyError

        try:
            result = AnalysisResult.model_validate(candidate)
        except (ValueError, PydanticDependencyError) as error:
            self.ledger.validation_error = str(redact_sensitive_value(str(error)))
            issue = ToolIssue(
                code=ToolErrorCode.CANDIDATE_SCHEMA,
                category="validation",
                message=self.ledger.validation_error,
                retryable=True,
            )
            self.control.record_issue(issue, allowed_next_actions=("validate_analysis",))
            return error_envelope(
                issue,
                allowed_next_actions=("validate_analysis",),
            )
        self.ledger.result = result
        self.ledger.validation_error = None
        self.control.protocol_issue = None
        self.control.next_actions = None
        self.control.phase = RunPhase.DONE
        return success_envelope(result.model_dump(mode="json"), meta={"terminal": True})

    def functions(self) -> list[object]:
        return list(self._tools)
