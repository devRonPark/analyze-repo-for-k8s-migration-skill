"""Dependency-free static MCP JSON-RPC schemas and response helpers."""
from __future__ import annotations

import json
from typing import Any

SERVER_INFO = {"name": "trusted-analysis-pipeline", "version": "0.2.0"}
STAGES = ("discovery", "execution", "relationships", "boundaries", "contracts")
STAGE_TOOL_BY_STAGE = {stage: f"submit_{stage}" for stage in STAGES}
TOOL_ORDER = (
    "start_analysis",
    "read_evidence",
    "list_target_paths",
    "locate_evidence",
    "get_target_git_metadata",
    "submit_discovery",
    "submit_execution",
    "submit_relationships",
    "submit_boundaries",
    "submit_contracts",
    "reopen_analysis",
    "finalize_analysis",
)

ERROR_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["code", "retryable", "issues"],
    "properties": {
        "code": {"type": "string"},
        "retryable": {"type": "boolean"},
        "issues": {"type": "array", "maxItems": 10, "items": {"type": "string", "maxLength": 300}},
    },
}
HANDOFF_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "analysis_id", "mode", "completed_stage", "revision", "transition_token", "next_skill", "accepted_output", "stage_input"],
    "properties": {
        "status": {"const": "accepted"},
        "analysis_id": {"type": "string", "pattern": "^an_[A-Za-z0-9_-]{8,}$"},
        "mode": {"type": "string", "enum": ["summary", "detailed"]},
        "completed_stage": {"type": ["string", "null"], "enum": [None, *STAGES]},
        "revision": {"type": "integer", "minimum": 0},
        "transition_token": {"type": "string", "pattern": "^tr_[A-Za-z0-9_-]{8,}$"},
        "next_skill": {"type": "string"},
        "accepted_output": {"type": "object"},
        "stage_input": {"type": "object"},
    },
}


def _tool(name: str, description: str, required: list[str], properties: dict[str, Any], *, read_only: bool = False) -> dict[str, Any]:
    value = {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": required,
            "properties": properties,
        },
        "outputSchema": {"oneOf": [HANDOFF_SCHEMA, ERROR_SCHEMA, {"type": "object"}]},
    }
    if read_only:
        value["annotations"] = {
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        }
    return value


_ENVELOPE = {
    "analysis_id": {"type": "string", "pattern": "^an_[A-Za-z0-9_-]{8,}$"},
    "revision": {"type": "integer", "minimum": 0},
    "transition_token": {"type": "string", "pattern": "^tr_[A-Za-z0-9_-]{8,}$"},
    "payload": {"type": "object"},
}

TOOLS = [
    _tool(
        "start_analysis",
        "Start a read-only local Git analysis for the selected target path and mode.",
        ["target_path", "mode"],
        {"target_path": {"type": "string", "minLength": 1}, "mode": {"type": "string", "enum": ["summary", "detailed"]}},
    ),
    _tool("read_evidence", "Read bounded redacted evidence from the active target.", ["path"], {"path": {"type": "string"}, "offset": {"type": "integer", "minimum": 0}, "limit": {"type": "integer", "minimum": 1, "maximum": 200}}, read_only=True),
    _tool("list_target_paths", "List bounded paths from the active target.", ["pattern"], {"pattern": {"type": "string"}, "path": {"type": "string"}}, read_only=True),
    _tool("locate_evidence", "Locate redacted evidence or a scoped absence in the active target.", ["glob"], {"glob": {"type": "string"}, "path": {"type": "string"}, "pattern": {"type": "string"}}, read_only=True),
    _tool("get_target_git_metadata", "Get the active target Git revision metadata.", [], {}, read_only=True),
]
TOOLS.extend(
    _tool(
        STAGE_TOOL_BY_STAGE[stage],
        (
            "Submit only when the current Discovery Vertical Slice has grounded its candidate claims. "
            "Submit observation aliases, never raw repository evidence."
            if stage == "discovery"
            else (
                "Submit only when the current Execution Vertical Slice has grounded its build, runtime, startup, image, or port claims. "
                "Submit observation aliases, never raw repository evidence."
                if stage == "execution"
                else (
                    "Submit only when the current Relationships Vertical Slice has grounded dependency and external runtime claims. "
                    "Submit observation aliases, never raw repository evidence."
                    if stage == "relationships"
                else f"Submit the current {stage} Vertical Slice with trusted observations."
                )
            )
        ),
        list(_ENVELOPE),
        dict(_ENVELOPE),
    )
    for stage in STAGES
)
TOOLS.extend(
    [
        _tool("reopen_analysis", "Reopen an accepted earlier stage after new evidence invalidates it.", ["analysis_id", "revision", "transition_token", "stage", "reason"], {"analysis_id": _ENVELOPE["analysis_id"], "revision": _ENVELOPE["revision"], "transition_token": _ENVELOPE["transition_token"], "stage": {"type": "string", "enum": list(STAGES)}, "reason": {"type": "string", "minLength": 3, "maxLength": 500}}),
        _tool("finalize_analysis", "Finalize accepted report state and return canonical Markdown.", ["analysis_id", "revision", "transition_token"], {key: _ENVELOPE[key] for key in ("analysis_id", "revision", "transition_token")}),
    ]
)
assert tuple(tool["name"] for tool in TOOLS) == TOOL_ORDER


def response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def text_result(value: Any, *, is_error: bool = False) -> dict[str, Any]:
    structured = value if isinstance(value, dict) else {"value": value}
    text = value if isinstance(value, str) else json.dumps(structured, ensure_ascii=False, sort_keys=True)
    result = {"content": [{"type": "text", "text": text[:24_000]}], "structuredContent": structured}
    if is_error:
        result["isError"] = True
    return result
