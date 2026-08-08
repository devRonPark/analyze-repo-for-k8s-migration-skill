import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis_pipeline.mcp_server import Server, catalog_changed_notification, handle


class MCPTests(unittest.TestCase):
    def test_initialize_advertises_catalog_changes(self):
        result = handle(Server(), {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertTrue(result["result"]["capabilities"]["tools"]["listChanged"])

    def test_catalog_change_notification_uses_standard_method(self):
        self.assertEqual(catalog_changed_notification()["method"], "notifications/tools/list_changed")

    def test_catalog_exposes_only_active_stage(self):
        server = Server()
        initial = handle(server, {"id": 1, "method": "tools/list"})
        self.assertEqual([item["name"] for item in initial["result"]["tools"]], ["start_analysis"])
        handle(server, {"id": 2, "method": "tools/call", "params": {"name": "start_analysis", "arguments": {"binding": "b"}}})
        active = handle(server, {"id": 3, "method": "tools/list"})
        self.assertTrue({"submit_discovery", "reopen_analysis", "read_evidence", "list_target_paths", "get_target_git_metadata", "locate_evidence"}.issubset({item["name"] for item in active["result"]["tools"]}))

    def test_second_start_is_rejected(self):
        server = Server()
        handle(server, {"id": 1, "method": "tools/call", "params": {"name": "start_analysis", "arguments": {"binding": "b"}}})
        self.assertIn("error", handle(server, {"id": 2, "method": "tools/call", "params": {"name": "start_analysis", "arguments": {"binding": "b"}}}))

    def test_read_evidence_is_available_only_after_start(self):
        server = Server()
        root = str(Path(__file__).resolve().parents[1])
        binding = {"binding_id": "b", "target_realpath": root, "target_snapshot_hash": "s", "skill_manifest_hash": "m", "required_rule_ids": []}
        handle(server, {"id": 1, "method": "tools/call", "params": {"name": "start_analysis", "arguments": {"binding": binding}}})
        result = handle(server, {"id": 2, "method": "tools/call", "params": {"name": "read_evidence", "arguments": {"path": "pyproject.toml"}}})
        self.assertIn("trusted-analysis-pipeline", result["result"]["structuredContent"])

    def test_unknown_method_is_error(self):
        self.assertIn("error", handle(Server(), {"id": 1, "method": "x"}))
