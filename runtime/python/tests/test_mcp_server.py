import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis_pipeline.mcp_server import Server, catalog_changed_notification, handle
from analysis_pipeline.protocol import text_result
from analysis_pipeline.state import derive_evidence_id
from analysis_pipeline.tools.locate_evidence import locate_evidence
from analysis_pipeline.tools.read import read, render_lines


class MCPTests(unittest.TestCase):
    @staticmethod
    def _payload(stage, binding):
        evidence = {
            "location": f"{stage}.md", "range": "1-1", "status": "confirmed",
            "content_fingerprint": f"{stage}-fingerprint", "redacted": True,
        }
        evidence_id = derive_evidence_id({"snapshot_hash": binding["target_snapshot_hash"], **evidence})
        payload = {
            "stage": stage,
            "claims": [{"id": f"{stage}-claim", "status": "confirmed", "evidence_ids": [evidence_id]}],
            "evidence_ids": [evidence_id], "evidence_inputs": {evidence_id: evidence}, "rule_applications": [],
        }
        payload.update({
            "discovery": {"signals": ["signal"], "candidate_ids": ["candidate"], "decisions": ["decision"]},
            "execution": {"process_ids": ["process"]},
            "relationships": {"graph_edge_ids": ["edge"]},
            "boundaries": {"unit_ids": ["unit"], "deployable_unit_ids": ["unit"], "decisions": ["decision"]},
            "contracts": {"contract_ids": ["contract"]},
        }[stage])
        return payload

    def test_initialize_advertises_catalog_changes(self):
        result = handle(Server(), {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertTrue(result["result"]["capabilities"]["tools"]["listChanged"])

    def test_catalog_change_notification_uses_standard_method(self):
        self.assertEqual(catalog_changed_notification()["method"], "notifications/tools/list_changed")

    def test_catalog_exposes_only_active_stage(self):
        server = Server(target_root=Path(__file__).resolve().parents[1])
        initial = handle(server, {"id": 1, "method": "tools/list"})
        self.assertEqual([item["name"] for item in initial["result"]["tools"]], ["start_analysis"])
        started = handle(server, {"id": 2, "method": "tools/call", "params": {"name": "start_analysis", "arguments": {}}})
        self.assertEqual(started["result"]["structuredContent"]["binding"]["target_realpath"], str(Path(__file__).resolve().parents[1]))
        active = handle(server, {"id": 3, "method": "tools/list"})
        self.assertTrue({"submit_discovery", "reopen_analysis", "read_evidence", "list_target_paths", "get_target_git_metadata", "locate_evidence"}.issubset({item["name"] for item in active["result"]["tools"]}))

    def test_second_start_is_rejected(self):
        server = Server()
        handle(server, {"id": 1, "method": "tools/call", "params": {"name": "start_analysis", "arguments": {}}})
        self.assertIn("error", handle(server, {"id": 2, "method": "tools/call", "params": {"name": "start_analysis", "arguments": {}}}))

    def test_identical_submit_retry_returns_original_receipt_and_conflict_is_rejected(self):
        server = Server(target_root=Path(__file__).resolve().parents[1])
        started = server.call({"action": "start", "arguments": {}})
        request = {
            "action": "submit", "stage": "discovery", "payload": self._payload("discovery", started["binding"]),
            "expected_revision": started["revision"], "expected_hash": started["state_hash"],
            "transition_token": started["transition_token"],
        }
        first = server.call(request)
        self.assertEqual(server.call(request), first)
        changed = {**request, "payload": {**request["payload"], "signals": ["different"]}}
        with self.assertRaisesRegex(ValueError, "replay conflict"):
            server.call(changed)

    def test_five_stage_submissions_expose_finalize_without_submit_finalize(self):
        server = Server(target_root=Path(__file__).resolve().parents[1])
        started = handle(server, {"id": 1, "method": "tools/call", "params": {"name": "start_analysis", "arguments": {}}})
        receipt = started["result"]["structuredContent"]
        for request_id, stage in enumerate(("discovery", "execution", "relationships", "boundaries", "contracts"), start=2):
            submitted = handle(server, {"id": request_id, "method": "tools/call", "params": {"name": f"submit_{stage}", "arguments": {
                "payload": self._payload(stage, receipt["binding"]),
                "expected_revision": receipt["revision"], "expected_hash": receipt["state_hash"], "transition_token": receipt["transition_token"],
            }}})
            receipt = submitted["result"]["structuredContent"]
        tools = [tool["name"] for tool in handle(server, {"id": 8, "method": "tools/list"})["result"]["tools"]]
        self.assertIn("finalize_analysis", tools)
        self.assertNotIn("submit_finalize", tools)
        finalized = handle(server, {"id": 9, "method": "tools/call", "params": {"name": "finalize_analysis", "arguments": {
            "expected_revision": receipt["revision"], "expected_hash": receipt["state_hash"], "transition_token": receipt["transition_token"],
        }}})
        self.assertTrue(finalized["result"]["structuredContent"]["finalized"])

    def test_read_evidence_is_available_only_after_start(self):
        server = Server(target_root=Path(__file__).resolve().parents[1])
        handle(server, {"id": 1, "method": "tools/call", "params": {"name": "start_analysis", "arguments": {}}})
        result = handle(server, {"id": 2, "method": "tools/call", "params": {"name": "read_evidence", "arguments": {"path": "pyproject.toml"}}})
        self.assertIn("trusted-analysis-pipeline", result["result"]["structuredContent"]["text"])
        self.assertTrue(result["result"]["structuredContent"]["observation_ref"].startswith("obs_"))

    def test_start_tool_does_not_accept_model_owned_binding(self):
        server = Server()
        result = handle(server, {"id": 1, "method": "tools/list"})
        start = result["result"]["tools"][0]
        self.assertEqual(start["inputSchema"]["required"], [])
        self.assertNotIn("binding", start["inputSchema"]["properties"])

    def test_structured_content_is_reserved_for_object_results(self):
        plain = text_result("plain text")
        self.assertNotIn("structuredContent", plain)
        self.assertEqual(plain["content"][0]["text"], "plain text")
        self.assertEqual(text_result({"fact": "value"})["structuredContent"], {"fact": "value"})

    def test_read_evidence_caps_default_and_requested_output(self):
        lines = [f"line {index}" for index in range(250)]
        default = render_lines(lines)
        requested = render_lines(lines, limit=10000)
        self.assertIn("[TRUNCATED", default)
        self.assertIn("[TRUNCATED", requested)
        self.assertLessEqual(len(default), 24_500)
        self.assertLessEqual(len(requested), 24_500)

    def test_locate_evidence_searches_a_file_scoped_path(self):
        root = Path(__file__).resolve().parent
        result = locate_evidence(root, "test_mcp_server.py", "test_mcp_server.py", "class MCPTests")
        self.assertEqual(result["status"], "found")
        self.assertTrue(result["reference"].startswith("test_mcp_server.py:"))

    def test_unknown_method_is_error(self):
        self.assertIn("error", handle(Server(), {"id": 1, "method": "x"}))
