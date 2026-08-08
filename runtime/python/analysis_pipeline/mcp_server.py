"""Local stdio MCP server; state and target binding exist only for this process."""
from __future__ import annotations
import hashlib, json, secrets, subprocess, sys
from pathlib import Path
from . import create_state, normalize_submission_payload, submit, reopen, finalize
from .observations import ObservationRegistry, TargetSnapshot
from .state import canonical_json
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
    def __init__(self, target_root=None):
        self.state = None
        self._target_root = Path(target_root or Path.cwd()).resolve()
        self._registry = None
        self._transition_token = None
        self._replay_ledger = {}

    def _binding(self):
        if not self._target_root.is_dir():
            raise ValueError("OpenCode workspace is unavailable")
        snapshot = TargetSnapshot.capture(self._target_root).digest
        return {
            "binding_id": "process_" + secrets.token_hex(16),
            "target_realpath": str(self._target_root),
            "target_snapshot_hash": snapshot,
            "skill_manifest_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "required_rule_ids": [],
        }

    def normalize_stage_payload(self, stage, payload):
        if self.state is None or self._registry is None:
            raise ValueError("analysis has not started")
        if not isinstance(payload, dict) or not isinstance(payload.get("evidence"), list):
            raise ValueError("evidence declarations required")
        snapshot = TargetSnapshot.capture(self._target_root)
        observations = {}
        for item in payload["evidence"]:
            if not isinstance(item, dict) or not isinstance(item.get("observation_ref"), str):
                raise ValueError("invalid evidence declaration")
            ref = item["observation_ref"]
            observations[ref] = self._registry.resolve(ref, stage, snapshot)
        return normalize_submission_payload(payload, observations, self.state.binding)

    def call(self, args):
        action = args.get("action")
        if action == "start":
            if self.state is not None: raise ValueError("active analysis already exists")
            if args.get("arguments"):
                raise ValueError("start_analysis accepts no model-supplied arguments")
            binding = self._binding()
            self.state = create_state(binding)
            self._registry = ObservationRegistry(self._target_root, binding)
            self._transition_token = "tr_" + secrets.token_urlsafe(18)
            self._replay_ledger = {}
            return self._state()
        token = args.get("transition_token")
        request_digest = hashlib.sha256(canonical_json(args).encode("utf-8")).hexdigest()
        replay = self._replay_ledger.get(token)
        if replay is not None:
            if replay["digest"] == request_digest:
                return replay["receipt"]
            raise ValueError("replay conflict")
        if self.state is None: raise ValueError("analysis has not started")
        if not isinstance(token, str) or token != self._transition_token:
            raise ValueError("stale transition token")
        if TargetSnapshot.capture(self._target_root).digest != self.state.binding["target_snapshot_hash"]:
            raise ValueError("target snapshot changed")
        rev, digest = args.get("expected_revision"), args.get("expected_hash")
        if action == "submit": self.state = submit(self.state, args.get("stage"), args.get("payload"), rev, digest)
        elif action == "reopen":
            self.state = reopen(self.state, args.get("stage"), args.get("reason"), rev, digest)
            self._registry.invalidate_from(self.state.current_stage)
        elif action == "finalize":
            self.state = finalize(self.state, rev, digest)
            result = self._state()
            self._replay_ledger[token] = {"digest": request_digest, "receipt": result}
            self.state = None; self._registry.clear(); self._registry = None; self._transition_token = None
            return result
        else: raise ValueError("unknown action")
        self._transition_token = "tr_" + secrets.token_urlsafe(18)
        result = self._state()
        self._replay_ledger[token] = {"digest": request_digest, "receipt": result}
        return result
    def _state(self):
        return {"binding": self.state.binding, "revision": self.state.revision, "current_stage": self.state.current_stage, "finalized": self.state.finalized, "state_hash": self.state.state_hash, "transition_token": self._transition_token}
    def target_root(self):
        if self.state is None:
            raise ValueError("verified target is unavailable")
        return self._target_root

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
            if name == "start_analysis": result = server.call({"action":"start", "arguments": args})
            elif name == "reopen_analysis": result = server.call({"action":"reopen", **args})
            elif name == "finalize_analysis": result = server.call({"action":"finalize", **args})
            elif name in STAGE_TOOL_BY_STAGE.values():
                stage = next(key for key, value in STAGE_TOOL_BY_STAGE.items() if value == name)
                normalized, _ = server.normalize_stage_payload(stage, args.get("payload"))
                result = server.call({"action":"submit", "stage":stage, **{**args, "payload": normalized}})
            elif name == "read_evidence": result = read(server.target_root(), **args, observation_registry=server._registry, stage=server.state.current_stage)
            elif name == "list_target_paths": result = glob_paths(server.target_root(), **args)
            elif name == "get_target_git_metadata": result = git_metadata(server.target_root())
            elif name == "locate_evidence": result = locate_evidence(server.target_root(), **args, observation_registry=server._registry, stage=server.state.current_stage)
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
