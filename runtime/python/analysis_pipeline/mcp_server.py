"""Static local stdio MCP server for one process-private analysis."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .protocol import SERVER_INFO, STAGE_TOOL_BY_STAGE, TOOLS, error, response, text_result
from .session import AnalysisSession
from .tools import git_metadata, glob_paths, locate_evidence, read


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

    def _error(self, code: str, issue: str, *, retryable: bool = False) -> dict[str, Any]:
        return {"code": code, "retryable": retryable, "issues": [issue]}

    def tool_call(self, name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        if not isinstance(arguments, dict):
            return self._error("invalid_arguments", "arguments_must_be_object"), True
        try:
            if name == "start_analysis":
                return self.session.start(arguments.get("target_path"), arguments.get("mode")), False
            self.session.assert_active()
            if name == "read_evidence":
                return read(self.session.target_root, **arguments, observation_registry=self.session.registry, stage=self.session.current_stage), False
            if name == "list_target_paths":
                return {"paths": glob_paths(self.session.target_root, **arguments).splitlines()}, False
            if name == "locate_evidence":
                return locate_evidence(self.session.target_root, **arguments, observation_registry=self.session.registry, stage=self.session.current_stage), False
            if name == "get_target_git_metadata":
                return {"metadata": git_metadata(self.session.target_root)}, False
            if name == "submit_discovery":
                return self.session.submit_discovery(arguments), False
            if name == "submit_execution":
                return self.session.submit_execution(arguments), False
            if name == "submit_relationships":
                return self.session.submit_relationships(arguments), False
            if name in STAGE_TOOL_BY_STAGE.values():
                self.session.assert_envelope(arguments)
                return self._error("stage_not_ready", "stage_payload_validation_is_not_delivered"), True
            if name == "reopen_analysis":
                self.session.assert_envelope(arguments)
                return self._error("reopen_not_ready", "reopen_is_not_delivered"), True
            if name == "finalize_analysis":
                self.session.assert_envelope(arguments)
                return self._error("finalize_not_ready", "finalize_is_not_delivered"), True
            raise KeyError(name)
        except KeyError:
            return self._error("invalid_submission", "invalid_submission"), True
        except (TypeError, ValueError, OSError) as exc:
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
        return response(request_id, text_result(result, is_error=is_error))
    return error(request_id, -32601, "method not found")


def main(command_directory: str | Path | None = None) -> None:
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
