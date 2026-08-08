"""Dependency-free MCP JSON-RPC schemas and response helpers."""
import json
from typing import Any

SERVER_INFO = {"name": "trusted-analysis-pipeline", "version": "0.1.0"}
STAGES = ("discovery", "execution", "relationships", "boundaries", "contracts")
STAGE_TOOL_BY_STAGE = {stage: f"submit_{stage}" for stage in STAGES}


def tool(name: str, description: str, required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "description": description, "inputSchema": {"type": "object", "required": required, "properties": properties}}


LIFECYCLE_TOOLS = [
    tool("start_analysis", "Start the process-private analysis for the current OpenCode workspace exactly once. Call with {}: do not provide a binding, ID, path, revision, mode, or goal. The server derives and owns the target binding, then returns only the active stage and concurrency token.", [], {}),
    tool("reopen_analysis", "Reopen an earlier accepted stage only when new evidence invalidates it. Provide a bounded reason and current revision/hash. This discards that stage and later outputs atomically; it cannot skip forward.", ["stage", "reason", "expected_revision", "expected_hash"], {"stage": {"type": "string"}, "reason": {"type": "string"}, "expected_revision": {"type": "integer"}, "expected_hash": {"type": "string"}}),
    tool("finalize_analysis", "Finalize only after all stage receipts are accepted. Revalidates evidence, mandatory rules, relationships, boundaries, and contracts, then clears process-private state on success.", ["expected_revision", "expected_hash"], {"expected_revision": {"type": "integer"}, "expected_hash": {"type": "string"}}),
]

STAGE_TOOLS = [tool(STAGE_TOOL_BY_STAGE[stage], f"Submit the {stage} vertical slice only when it is the active stage. Ground claims in target evidence and applicable rules, and send the current revision/hash. Do not submit another or future stage.", ["payload", "expected_revision", "expected_hash"], {"payload": {"type": "object"}, "expected_revision": {"type": "integer"}, "expected_hash": {"type": "string"}}) for stage in STAGES]

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
