"""Small, dependency-free MCP JSON-RPC boundary."""
import json
from typing import Any

SERVER_INFO = {"name": "trusted-analysis-pipeline", "version": "0.1.0"}
_RECEIPT = {"type": "object", "properties": {"revision": {"type": "integer"}, "state_hash": {"type": "string"}, "current_stage": {"type": "string"}}}
TOOLS = [{"name": "analysis_start", "description": "Call once at the beginning, before any stage tool. Starts one process-private analysis; a second start is rejected. The receipt provides the active stage and revision/hash token.", "inputSchema": {"type": "object", "required": ["binding"], "properties": {"binding": {"type": "object"}}}}, {"name": "analysis_reopen", "description": "Call only when new evidence invalidates an earlier accepted stage. Provide a bounded reason and current revision/hash. The selected stage and all later outputs are atomically discarded; this never skips forward.", "inputSchema": {"type": "object", "required": ["stage", "reason", "expected_revision", "expected_hash"], "properties": {"stage": {"type": "string"}, "reason": {"type": "string"}, "expected_revision": {"type": "integer"}, "expected_hash": {"type": "string"}}}}, *[{"name": f"analysis_{stage}", "description": f"Call only when the receipt names {stage} as active. Submit its closed contract with grounded claims, evidence, and applicable rules plus the current revision/hash. Do not submit future-stage data or another stage; success advances the active stage.", "inputSchema": {"type": "object", "required": ["payload", "expected_revision", "expected_hash"], "properties": {"payload": {"type": "object"}, "expected_revision": {"type": "integer"}, "expected_hash": {"type": "string"}}}} for stage in ("discovery", "execution", "relationships", "boundaries", "contracts")], {"name": "analysis_finalize", "description": "Call only after every stage receipt is accepted. Revalidates mandatory rules, evidence provenance, relationships, boundaries, and contracts; on success returns the final report and immediately clears process-private state.", "inputSchema": {"type": "object", "required": ["expected_revision", "expected_hash"], "properties": {"expected_revision": {"type": "integer"}, "expected_hash": {"type": "string"}}}}]

def response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}

def error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

def text_result(value: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, sort_keys=True)}], "structuredContent": value}
