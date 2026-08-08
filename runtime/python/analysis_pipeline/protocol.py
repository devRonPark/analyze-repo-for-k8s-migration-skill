"""Small, dependency-free MCP JSON-RPC boundary."""
import json
from typing import Any

SERVER_INFO = {"name": "trusted-analysis-pipeline", "version": "0.1.0"}
TOOL = {"name": "analysis_pipeline", "description": "Run the trusted six-stage analysis pipeline.", "inputSchema": {"type": "object", "required": ["action"], "properties": {"action": {"type": "string", "enum": ["start", "submit", "reopen", "finalize"]}, "binding": {"type": "object"}, "stage": {"type": "string"}, "payload": {"type": "object"}, "reason": {"type": "string"}, "expected_revision": {"type": "integer"}, "expected_hash": {"type": "string"}}}}

def response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}

def error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

def text_result(value: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, sort_keys=True)}], "structuredContent": value}
