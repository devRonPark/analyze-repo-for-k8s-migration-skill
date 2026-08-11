"""Static local stdio MCP server for one process-private analysis."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .protocol import SERVER_INFO, STAGE_TOOL_BY_STAGE, TOOLS, error, markdown_result, response, text_result
from .session import SUBMIT_REJECTION_LIMIT, AnalysisSession
from .stage_contracts import candidate_exclusion_contract, relationship_edge_contract, report_state_contract, workload_unit_contract
from .tools import git_metadata, glob_paths, locate_evidence, read

# Stage submits and finalize_analysis share the bounded retry budget.  The
# catalog deliberately omits the undelivered reopen operation: exposing a
# permanent-failure action created a live retry loop without offering a valid
# correction.
RETRY_BUDGET_TOOLS = (*STAGE_TOOL_BY_STAGE.values(), "finalize_analysis")
NON_PAYLOAD_ERROR_CODES = frozenset({"invalid_arguments", "invalid_submission"})


def catalog_changed_notification() -> None:
    """Static catalogs never emit a list-changed notification."""
    return None


class Server:
    def __init__(
        self,
        command_directory: str | Path | None = None,
        target_root: str | Path | None = None,
    ) -> None:
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

    def _error(self, code: str, issue: str, *, retryable: bool = False) -> dict[str, Any]:
        return {"code": code, "retryable": retryable, "issues": [issue]}

    def _validation_error(self, message: str) -> dict[str, Any]:
        """Return a deterministic correction for the reproduced edge-format loop."""
        if message == "invalid relationship mechanism":
            return {
                "code": "invalid_relationship_mechanism",
                "retryable": True,
                "issues": [
                    "payload.graph_edges[].mechanism must be an identifier matching ^[A-Za-z][A-Za-z0-9_.-]{0,63}$; use a machine identifier such as jdbc or spring_boot, not descriptive prose",
                ],
            }
        if message.startswith("report slots must exactly match server-selected ids"):
            return {
                "code": "report_slot_set_mismatch",
                "retryable": True,
                "issues": [
                    "payload.report_slots[].id must contain each server-selected id exactly once; " + message,
                ],
            }
        if message.startswith("relationship edge field errors:"):
            return {
                "code": "invalid_relationship_edge_fields",
                "retryable": True,
                "issues": [message],
            }
        return self._error(message, message)

    def _budget(self) -> dict[str, int]:
        return {
            "submit_rejections_remaining": max(0, SUBMIT_REJECTION_LIMIT - self.session.submit_rejections),
        }

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
        if is_error and name == "submit_boundaries":
            recovery_class = self.session.observe_boundaries_rejection(arguments.get("payload"), result)
            if recovery_class is not None:
                try:
                    return self.session.recover_boundaries(recovery_class), False
                except (TypeError, ValueError, OSError) as exc:
                    return self._error("boundaries_recovery_unavailable", str(exc)), True
        if is_error and name in RETRY_BUDGET_TOOLS and result["code"] not in NON_PAYLOAD_ERROR_CODES:
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
        return result, is_error

    def _dispatch(self, name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        if not isinstance(arguments, dict):
            return self._error("invalid_arguments", "arguments_must_be_object"), True
        try:
            if name == "start_analysis":
                return self.session.start(arguments.get("target_path"), arguments.get("mode")), False
            self.session.assert_active()
            if name == "read_evidence":
                result = read(self.session.target_root, **arguments, observation_registry=self.session.registry, stage=self.session.current_stage)
                return {**result, "budget": self._budget()}, False
            if name == "list_target_paths":
                paths = glob_paths(self.session.target_root, **arguments).splitlines()
                return {"paths": paths, "budget": self._budget()}, False
            if name == "locate_evidence":
                result = locate_evidence(self.session.target_root, **arguments, observation_registry=self.session.registry, stage=self.session.current_stage)
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
        except KeyError:
            return self._error("invalid_submission", "invalid_submission"), True
        except (TypeError, ValueError, OSError) as exc:
            if str(exc) == "stage_order" and name == "finalize_analysis":
                stage = self.session.current_stage or "current"
                return self._error(
                    "stage_order",
                    f"{stage} remains open; correct its rejection and call submit_{stage}. finalize_analysis is valid only after submit_contracts is accepted",
                ), True
            if str(exc) == "observation stage mismatch":
                stage = self.session.current_stage or "current"
                return self._error(
                    "observation_stage_mismatch",
                    f"payload.evidence observation_ref values must be issued in the current {stage} stage; incoming *_fact_refs are accepted facts, not observation_ref values",
                    retryable=True,
                ), True
            if issue := self._nested_contract_issue(str(exc)):
                return self._error("invalid_nested_stage_payload", issue, retryable=True), True
            return self._validation_error(str(exc)), True


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
