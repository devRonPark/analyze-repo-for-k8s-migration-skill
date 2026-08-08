"""Small, dependency-free MCP JSON-RPC boundary."""
import json
from typing import Any

SERVER_INFO = {"name": "trusted-analysis-pipeline", "version": "0.1.0"}
_RECEIPT = {"type": "object", "properties": {"revision": {"type": "integer"}, "state_hash": {"type": "string"}, "current_stage": {"type": "string"}}}
TOOLS = [{"name": "analysis_start", "description": "Start one process-private analysis.", "inputSchema": {"type": "object", "required": ["binding"], "properties": {"binding": {"type": "object"}}}}, {"name": "analysis_reopen", "description": "Reopen an explicitly permitted prior stage.", "inputSchema": {"type": "object", "required": ["stage", "reason", "expected_revision", "expected_hash"], "properties": {"stage": {"type": "string"}, "reason": {"type": "string"}, "expected_revision": {"type": "integer"}, "expected_hash": {"type": "string"}}}}, *[{"name": f"analysis_{stage}", "description": f"Submit the {stage} stage contract.", "inputSchema": {"type": "object", "required": ["payload", "expected_revision", "expected_hash"], "properties": {"payload": {"type": "object"}, "expected_revision": {"type": "integer"}, "expected_hash": {"type": "string"}}}} for stage in ("discovery", "execution", "relationships", "boundaries", "contracts")], {"name": "analysis_finalize", "description": "Validate and finalize the completed analysis.", "inputSchema": {"type": "object", "required": ["expected_revision", "expected_hash"], "properties": {"expected_revision": {"type": "integer"}, "expected_hash": {"type": "string"}}}}]

def response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}

def error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

def text_result(value: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, sort_keys=True)}], "structuredContent": value}
