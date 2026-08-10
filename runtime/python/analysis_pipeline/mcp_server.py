"""Static local stdio MCP server for one process-private analysis."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .protocol import SERVER_INFO, STAGE_TOOL_BY_STAGE, TOOLS, error, markdown_result, response, text_result
from .session import PRECISION_CALL_LIMIT, SUBMIT_REJECTION_LIMIT, AnalysisSession
from .stage_contracts import (
    StagePayloadContractError,
    StagePayloadValidationError,
    candidate_exclusion_contract,
    relationship_edge_contract,
    report_state_contract,
    workload_unit_contract,
)
from .tools import git_metadata, glob_paths, locate_evidence, read
from .validation import EvidenceAliasContractError

PRECISION_BUDGET_TOOLS = ("read_evidence", "locate_evidence", "list_target_paths")
# Only the submit tool for the active stage consumes this stage's correction
# budget. Other control calls and out-of-order submissions stay diagnostic.
NON_PAYLOAD_ERROR_CODES = frozenset({"invalid_arguments", "invalid_submission"})


def catalog_changed_notification() -> None:
    """Static catalogs never emit a list-changed notification."""
    return None


class Server:
    def __init__(self, command_directory: str | Path | None = None, target_root: str | Path | None = None) -> None:
        directory = Path(command_directory or target_root or Path.cwd()).resolve()
        self.session = AnalysisSession(directory)
        self.command_directory = directory

    @property
    def state(self) -> Any:
        return self.session if self.session.active else None

    def call(self, arguments: dict[str, Any]) -> dict[str, Any]:
        action = arguments.get("action")
        if action == "start":
            supplied = arguments.get("arguments", {})
            return self.session.start(supplied.get("target_path"), supplied.get("mode"))
        raise ValueError("unsupported_direct_action")

    def _error(self, code: str, issue: str, *, retryable: bool = False, **details: Any) -> dict[str, Any]:
        return {"code": code, "retryable": retryable, "issues": [issue], **details}

    def _stage_payload_error(self, exc: StagePayloadContractError | StagePayloadValidationError) -> dict[str, Any]:
        if isinstance(exc, StagePayloadContractError):
            return self._error(
                "invalid_stage_payload",
                f"payload does not match the {exc.stage} contract; correct the listed fields and submit again",
                retryable=True,
                stage=exc.stage,
                missing_fields=exc.missing_fields,
                unexpected_fields=exc.unexpected_fields,
                required_fields=exc.required_fields,
            )
        return self._error("invalid_stage_payload", exc.issue, retryable=True, stage=exc.stage)

    def _budget(self) -> dict[str, int]:
        return {
            "precision_calls_remaining": max(0, PRECISION_CALL_LIMIT - self.session.precision_calls_used),
            "submit_rejections_remaining": max(0, SUBMIT_REJECTION_LIMIT - self.session.submit_rejections),
        }

    def _precision_budget_error(self) -> dict[str, Any]:
        stage = self.session.current_stage or "current"
        return self._error(
            "precision_budget_exhausted",
            (
                f"the current {stage} stage's one-call content-search budget "
                "(read_evidence/locate_evidence/list_target_paths) is exhausted; "
                "submit now with unknown/inferred status for anything still ungrounded"
            ),
        )

    @staticmethod
    def _nested_contract_issue(message: str) -> str | None:
        contracts = {
            "unknown relationship edge field": ("payload.graph_edges[]", relationship_edge_contract()),
            "unknown workload unit field": ("payload.workload_units[]", workload_unit_contract()),
            "unknown candidate exclusion field": ("payload.candidate_exclusions[]", candidate_exclusion_contract()),
            "unknown report slot field": ("payload.report_slots[]", report_state_contract()["report_slot"]),
        }
        entry = contracts.get(message)
        if entry is None:
            return None
        path, contract = entry
        return f"{path} permits only: {', '.join(sorted(contract))}"

    def tool_call(self, name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        result, is_error = self._dispatch(name, arguments)
        current_stage_submit = STAGE_TOOL_BY_STAGE.get(self.session.current_stage)
        if is_error and name == current_stage_submit and result["code"] not in NON_PAYLOAD_ERROR_CODES:
            self.session.submit_rejections += 1
            if self.session.submit_rejections > SUBMIT_REJECTION_LIMIT:
                stage = self.session.current_stage or "current"
                result = self._error(
                    result["code"],
                    (
                        f"{result['issues'][0]} - this is beyond the current {stage} stage's "
                        "submission retry budget; resubmitting the same payload will not succeed, "
                        "resolve the specific issue above or submit with unknown/inferred status on "
                        "whatever it cannot ground"
                    ),
                )
            else:
                result["budget"] = self._budget()
        return result, is_error

    def _dispatch(self, name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        if not isinstance(arguments, dict):
            return self._error("invalid_arguments", "arguments_must_be_object"), True
        try:
            if name == "start_analysis":
                return self.session.start(arguments.get("target_path"), arguments.get("mode")), False
            self.session.assert_active()
            if name in PRECISION_BUDGET_TOOLS and self.session.precision_calls_used >= PRECISION_CALL_LIMIT:
                return self._precision_budget_error(), True
            if name == "read_evidence":
                result = read(self.session.target_root, **arguments, observation_registry=self.session.registry, stage=self.session.current_stage)
                self.session.precision_calls_used += 1
                return {**result, "budget": self._budget()}, False
            if name == "list_target_paths":
                paths = glob_paths(self.session.target_root, **arguments).splitlines()
                self.session.precision_calls_used += 1
                return {"paths": paths, "budget": self._budget()}, False
            if name == "locate_evidence":
                result = locate_evidence(self.session.target_root, **arguments, observation_registry=self.session.registry, stage=self.session.current_stage)
                self.session.precision_calls_used += 1
                return {**result, "budget": self._budget()}, False
            if name == "get_target_git_metadata":
                return {"metadata": git_metadata(self.session.target_root), "budget": self._budget()}, False
            if name == "submit_discovery":
                return self.session.submit_discovery(arguments.get("payload")), False
            if name == "submit_execution":
                return self.session.submit_execution(arguments.get("payload")), False
            if name == "submit_relationships":
                return self.session.submit_relationships(arguments.get("payload")), False
            if name == "submit_boundaries":
                return self.session.submit_boundaries(arguments.get("payload")), False
            if name == "submit_contracts":
                return self.session.submit_contracts(arguments.get("payload")), False
            if name == "finalize_analysis":
                return self.session.finalize_and_render(), False
            raise KeyError(name)
        except StagePayloadContractError as exc:
            return self._stage_payload_error(exc), True
        except StagePayloadValidationError as exc:
            return self._stage_payload_error(exc), True
        except EvidenceAliasContractError as exc:
            return self._error(
                "invalid_evidence_alias",
                "use payload.evidence[].alias values in claims, semantic facts, and rules; never use survey references as aliases",
                retryable=True,
                stage=self.session.current_stage or "current",
                path=exc.path,
            ), True
        except KeyError:
            return self._error("invalid_submission", "invalid_submission"), True
        except (TypeError, ValueError, OSError) as exc:
            if str(exc) == "observation stage mismatch":
                stage = self.session.current_stage or "current"
                return self._error(
                    "observation_stage_mismatch",
                    f"payload.evidence observation_ref values must be issued in the current {stage} stage; incoming *_fact_refs are accepted facts, not observation_ref values",
                    retryable=True,
                ), True
            if issue := self._nested_contract_issue(str(exc)):
                return self._error("invalid_nested_stage_payload", issue, retryable=True), True
            return self._error(str(exc), str(exc)), True


def handle(server: Server, request: dict[str, Any]) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params", {})
    if method == "initialize":
        return response(
            request_id,
            {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return response(request_id, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        if name not in {tool["name"] for tool in TOOLS}:
            return error(request_id, -32601, "unknown tool")
        result, is_error = server.tool_call(name, params.get("arguments", {}))
        if name == "finalize_analysis" and not is_error:
            try:
                structured = {key: result[key] for key in ("status", "analysis_id", "mode", "revision")}
                final_response = response(request_id, markdown_result(result["markdown"], structured))
            except (KeyError, TypeError, ValueError) as exc:
                return response(request_id, text_result(server._error("finalize_response_failed", str(exc)), is_error=True))
            server.session.clear()
            return final_response
        return response(request_id, text_result(result, is_error=is_error))
    return error(request_id, -32601, "method not found")


def main(command_directory: str | Path | None = None) -> None:
    # JSON-RPC over stdio must not depend on the parent process's console
    # codepage. Korean report text and non-ASCII punctuation in error
    # messages are both routine here; on a non-UTF-8 default (e.g. cp949 on
    # Korean Windows), an un-reconfigured stdout raises UnicodeEncodeError
    # on the first such character and silently kills this process, which
    # the client only sees as a dropped connection.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    server = Server(command_directory=command_directory or Path.cwd())
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            print(json.dumps(error(None, -32700, str(exc)), separators=(",", ":")), flush=True)
            continue
        result = handle(server, request)
        if result is not None:
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
