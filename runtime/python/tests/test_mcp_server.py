import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis_pipeline.mcp_server import Server, catalog_changed_notification, handle
from analysis_pipeline.protocol import TOOL_ORDER


class MCPTests(unittest.TestCase):
    def fixture(self, name: str = "external target") -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temporary = tempfile.TemporaryDirectory(dir=Path(os.environ["SystemRoot"]) / "Temp")
        command_directory = Path(temporary.name) / "command"
        target = command_directory if name == "." else command_directory / name
        target.mkdir(parents=True)
        subprocess.run(["git", "init"], cwd=target, check=True, capture_output=True)
        (target / "README.md").write_text("safe target\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=target, check=True, capture_output=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture"], cwd=target, check=True, capture_output=True)
        return temporary, command_directory, target

    def start(self, server: Server, target_path: str = "external target", mode: str = "summary") -> dict:
        return handle(server, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "start_analysis", "arguments": {"target_path": target_path, "mode": mode}}})

    def test_static_catalog_and_start_handoff_bind_external_target(self):
        temporary, command_directory, _ = self.fixture("외부 저장소")
        with temporary:
            server = Server(command_directory=command_directory)
            initial = handle(server, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]
            started = self.start(server, "외부 저장소")
            repeated = handle(server, {"jsonrpc": "2.0", "id": 3, "method": "tools/list"})["result"]["tools"]

        self.assertEqual([tool["name"] for tool in initial], list(TOOL_ORDER))
        self.assertEqual(json.dumps(initial, sort_keys=True), json.dumps(repeated, sort_keys=True))
        handoff = started["result"]["structuredContent"]
        self.assertEqual(handoff["completed_stage"], None)
        self.assertEqual(handoff["next_skill"], "analyze-k8s-discovery")
        self.assertEqual(handoff["mode"], "summary")

    def test_initialize_has_no_catalog_change_capability(self):
        result = handle(Server(), {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertNotIn("listChanged", result["result"]["capabilities"]["tools"])
        self.assertIsNone(catalog_changed_notification())

    def test_start_requires_a_target_path_and_mode(self):
        result = handle(Server(), {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "start_analysis", "arguments": {}}})
        self.assertTrue(result["result"]["isError"])
        self.assertEqual(result["result"]["structuredContent"]["code"], "target_path_required")

    def test_second_start_is_a_tool_error_without_state_change(self):
        temporary, command_directory, _ = self.fixture()
        with temporary:
            server = Server(command_directory=command_directory)
            accepted = self.start(server)["result"]["structuredContent"]
            rejected = self.start(server)["result"]
        self.assertTrue(rejected["isError"])
        self.assertEqual(rejected["structuredContent"]["code"], "analysis_already_active")
        self.assertEqual(server.session.analysis_id, accepted["analysis_id"])

    def test_submit_envelope_is_static_and_payload_is_opaque(self):
        tools = handle(Server(), {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]
        submit = next(tool for tool in tools if tool["name"] == "submit_discovery")
        schema = submit["inputSchema"]
        self.assertEqual(schema["required"], ["analysis_id", "revision", "transition_token", "payload"])
        self.assertEqual(schema["properties"]["payload"], {"type": "object"})
        evidence = next(tool for tool in tools if tool["name"] == "read_evidence")
        self.assertEqual(evidence["annotations"]["readOnlyHint"], True)
        self.assertEqual(evidence["annotations"]["destructiveHint"], False)

    def test_read_evidence_requires_an_active_analysis(self):
        result = handle(Server(), {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "read_evidence", "arguments": {"path": "README.md"}}})
        self.assertTrue(result["result"]["isError"])
        self.assertEqual(result["result"]["structuredContent"]["code"], "analysis_not_started")

    def test_relative_target_uses_process_start_command_directory(self):
        first, first_command, _ = self.fixture(".")
        second, second_command, _ = self.fixture("second")
        with first, second:
            first_result = self.start(Server(command_directory=first_command), ".")["result"]["structuredContent"]
            second_result = self.start(Server(command_directory=second_command), "second")["result"]["structuredContent"]
        self.assertNotEqual(first_result["analysis_id"], second_result["analysis_id"])
        self.assertEqual(first_result["completed_stage"], None)
        self.assertEqual(second_result["completed_stage"], None)


if __name__ == "__main__":
    unittest.main()
