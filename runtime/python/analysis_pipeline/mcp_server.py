"""Local stdio MCP server; state exists only for this process."""
from __future__ import annotations
import json, sys
from dataclasses import asdict
from . import create_state, submit, reopen, finalize
from .protocol import SERVER_INFO, TOOL, error, response, text_result

class Server:
    def __init__(self): self.state = None
    def call(self, args):
        action = args.get("action")
        if action == "start":
            if self.state is not None: raise ValueError("active analysis already exists")
            self.state = create_state(args.get("binding"))
            return self._state()
        if self.state is None: raise ValueError("analysis has not started")
        rev, digest = args.get("expected_revision"), args.get("expected_hash")
        if action == "submit": self.state = submit(self.state, args.get("stage"), args.get("payload"), rev, digest)
        elif action == "reopen": self.state = reopen(self.state, args.get("stage"), args.get("reason"), rev, digest)
        elif action == "finalize":
            self.state = finalize(self.state, rev, digest)
            result = self._state(); self.state = None
            return result
        else: raise ValueError("unknown action")
        return self._state()
    def _state(self):
        return {"binding": self.state.binding, "revision": self.state.revision, "current_stage": self.state.current_stage, "finalized": self.state.finalized, "state_hash": self.state.state_hash}

def handle(server, request):
    rid = request.get("id")
    method = request.get("method")
    try:
        if method == "initialize": return response(rid, {"protocolVersion": request.get("params", {}).get("protocolVersion", "2024-11-05"), "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO})
        if method == "notifications/initialized": return None
        if method == "tools/list": return response(rid, {"tools": [TOOL]})
        if method == "tools/call":
            params = request.get("params", {})
            if params.get("name") != TOOL["name"]: raise ValueError("unknown tool")
            return response(rid, text_result(server.call(params.get("arguments", {}))))
        raise ValueError("method not found")
    except (ValueError, TypeError, KeyError) as exc:
        return error(rid, -32602, str(exc))

def main():
    server = Server()
    for line in sys.stdin:
        try:
            request = json.loads(line); result = handle(server, request)
            if result is not None: print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)
        except json.JSONDecodeError as exc:
            print(json.dumps(error(None, -32700, str(exc)), separators=(",", ":")), flush=True)

if __name__ == "__main__": main()
