"""Dependency-free MCP JSON-RPC schemas and response helpers."""
import json
from typing import Any

SERVER_INFO = {"name": "trusted-analysis-pipeline", "version": "0.1.0"}
STAGES = ("discovery", "execution", "relationships", "boundaries", "contracts")
STAGE_TOOL_BY_STAGE = {stage: f"submit_{stage}" for stage in STAGES}


def tool(name: str, description: str, required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "description": description, "inputSchema": {"type": "object", "additionalProperties": False, "required": required, "properties": properties}}


LIFECYCLE_TOOLS = [
    tool("start_analysis", "Start the process-private analysis for the current OpenCode workspace exactly once. Call with {}: do not provide a binding, ID, path, revision, mode, or goal. The server derives and owns the target binding, then returns only the active stage and concurrency token.", [], {}),
    tool("reopen_analysis", "Reopen an earlier accepted stage only when new evidence invalidates it. Provide a bounded reason, current receipt, and transition token.", ["stage", "reason", "expected_revision", "expected_hash", "transition_token"], {"stage": {"type": "string"}, "reason": {"type": "string", "minLength": 3, "maxLength": 500}, "expected_revision": {"type": "integer", "minimum": 0}, "expected_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"}, "transition_token": {"type": "string", "pattern": "^tr_[A-Za-z0-9_-]{8,}$"}}),
    tool("finalize_analysis", "Finalize only after all stage receipts are accepted. Revalidates evidence and clears process-private state on success.", ["expected_revision", "expected_hash", "transition_token"], {"expected_revision": {"type": "integer", "minimum": 0}, "expected_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"}, "transition_token": {"type": "string", "pattern": "^tr_[A-Za-z0-9_-]{8,}$"}}),
]

def _string_list() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_.-]{0,63}$"}, "maxItems": 100}


def _submit_schema(stage: str) -> dict[str, Any]:
    evidence = {
        "type": "array", "minItems": 1, "maxItems": 100,
        "items": {"type": "object", "additionalProperties": False, "required": ["alias", "observation_ref"], "properties": {
            "alias": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_.-]{0,63}$"},
            "observation_ref": {"type": "string", "pattern": "^obs_[A-Za-z0-9_-]{8,}$"},
        }},
    }
    claims = {"type": "array", "maxItems": 200, "items": {"type": "object", "additionalProperties": False,
        "required": ["id", "status", "evidence_aliases"], "properties": {
            "id": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_.-]{0,63}$"},
            "status": {"type": "string", "enum": ["confirmed", "inferred", "unknown", "conflicted", "not_applicable"]},
            "evidence_aliases": _string_list(), "scope": {"type": "string", "maxLength": 500}, "blocked_decision": {"type": "string", "maxLength": 500},
        }}}
    rules = {"type": "array", "maxItems": 100, "items": {"type": "object", "additionalProperties": False,
        "required": ["rule_id", "evidence_aliases", "process_or_candidate_ids", "decision_id"], "properties": {
            "rule_id": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_.-]{0,63}$"}, "evidence_aliases": _string_list(),
            "process_or_candidate_ids": _string_list(), "decision_id": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_.-]{0,63}$"},
        }}}
    specific = {
        "discovery": {"signals": _string_list(), "candidate_ids": _string_list(), "decisions": _string_list()},
        "execution": {"process_ids": _string_list()}, "relationships": {"graph_edge_ids": _string_list()},
        "boundaries": {"unit_ids": _string_list(), "deployable_unit_ids": _string_list(), "decisions": _string_list()},
        "contracts": {"contract_ids": _string_list()},
    }[stage]
    payload_properties = {"schema_version": {"type": "integer", "enum": [1]}, "stage": {"type": "string", "enum": [stage]}, "evidence": evidence, "claims": claims, "rule_applications": rules, **specific}
    return {"type": "object", "additionalProperties": False, "required": ["schema_version", "stage", "evidence", "claims", "rule_applications", *specific.keys()], "properties": payload_properties}


STAGE_TOOLS = [tool(STAGE_TOOL_BY_STAGE[stage], f"Submit the current {stage} evidence slice only when this tool is advertised. Use only server-issued observation references and the receipt transition token.", ["payload", "expected_revision", "expected_hash", "transition_token"], {"payload": _submit_schema(stage), "expected_revision": {"type": "integer", "minimum": 0}, "expected_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"}, "transition_token": {"type": "string", "pattern": "^tr_[A-Za-z0-9_-]{8,}$"}}) for stage in STAGES]

TRUSTED_TOOLS = [
    tool("read_evidence", "Read a target file or directory whenever a current-stage claim needs source evidence. Use offset and limit for focused reads. Credential literals are redacted; paths outside the verified target are rejected.", ["path"], {"path": {"type": "string"}, "offset": {"type": "integer"}, "limit": {"type": "integer"}}),
    tool("list_target_paths", "List target paths matching a glob when choosing evidence files for the active stage. This returns paths only, never file contents, and caps results at 100.", ["pattern"], {"pattern": {"type": "string"}, "path": {"type": "string"}}),
    tool("get_target_git_metadata", "Get only the verified target's current Git branch and commit for report metadata. Do not use it to inspect history, diff, remotes, or repository content.", [], {}),
    tool("locate_evidence", "Locate a current-stage target fact by glob and optional regex before citing it. Use its returned repository-relative reference; when nothing matches, preserve the returned scoped absence.", ["glob"], {"glob": {"type": "string"}, "path": {"type": "string"}, "pattern": {"type": "string"}}),
]


def response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def text_result(value: Any) -> dict[str, Any]:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    result = {"content": [{"type": "text", "text": text}]}
    if isinstance(value, dict):
        result["structuredContent"] = value
    return result
