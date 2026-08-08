"""Local stdio MCP server; state exists only for this process."""
from __future__ import annotations
import json, sys
from . import create_state, submit, reopen, finalize
from .protocol import LIFECYCLE_TOOLS, SERVER_INFO, STAGE_TOOL_BY_STAGE, STAGE_TOOLS, TRUSTED_TOOLS, error, response, text_result
from .tools import git_metadata, glob_paths, locate_evidence, read

def visible_tools(server):
    if server.state is None:
        return [tool for tool in LIFECYCLE_TOOLS if tool["name"] == "start_analysis"]
    stage = server.state.current_stage
    if stage == "finalize":
        return [tool for tool in LIFECYCLE_TOOLS if tool["name"] in ("reopen_analysis", "finalize_analysis")] + TRUSTED_TOOLS
    return [tool for tool in LIFECYCLE_TOOLS if tool["name"] == "reopen_analysis"] + [tool for tool in STAGE_TOOLS if tool["name"] == STAGE_TOOL_BY_STAGE[stage]] + TRUSTED_TOOLS


def catalog_changed_notification():
    return {"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}

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
    def target_root(self):
        if self.state is None or not self.state.binding["target_realpath"]:
            raise ValueError("verified target is unavailable")
        return self.state.binding["target_realpath"]

def handle(server, request):
    rid = request.get("id")
    method = request.get("method")
    try:
        if method == "initialize": return response(rid, {"protocolVersion": request.get("params", {}).get("protocolVersion", "2024-11-05"), "capabilities": {"tools": {"listChanged": True}}, "serverInfo": SERVER_INFO})
        if method == "notifications/initialized": return None
        if method == "tools/list": return response(rid, {"tools": visible_tools(server)})
        if method == "tools/call":
            params = request.get("params", {})
            name, args = params.get("name"), params.get("arguments", {})
            if name == "start_analysis": result = server.call({"action":"start", **args})
            elif name == "reopen_analysis": result = server.call({"action":"reopen", **args})
            elif name == "finalize_analysis": result = server.call({"action":"finalize", **args})
            elif name in STAGE_TOOL_BY_STAGE.values():
                stage = next(key for key, value in STAGE_TOOL_BY_STAGE.items() if value == name)
                result = server.call({"action":"submit", "stage":stage, **args})
            elif name == "read_evidence": result = read(server.target_root(), **args)
            elif name == "list_target_paths": result = glob_paths(server.target_root(), **args)
            elif name == "get_target_git_metadata": result = git_metadata(server.target_root())
            elif name == "locate_evidence": result = locate_evidence(server.target_root(), **args)
            else: raise ValueError("unknown tool")
            return response(rid, text_result(result))
        raise ValueError("method not found")
    except (ValueError, TypeError, KeyError) as exc:
        return error(rid, -32602, str(exc))

def main():
    server = Server()
    for line in sys.stdin:
        try:
            request = json.loads(line); result = handle(server, request)
            if result is not None:
                print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)
                tool_name = request.get("params", {}).get("name", "")
                if request.get("method") == "tools/call" and (tool_name.endswith("analysis") or tool_name.startswith("submit_")) and "result" in result:
                    print(json.dumps(catalog_changed_notification(), separators=(",", ":")), flush=True)
        except json.JSONDecodeError as exc:
            print(json.dumps(error(None, -32700, str(exc)), separators=(",", ":")), flush=True)

if __name__ == "__main__": main()
