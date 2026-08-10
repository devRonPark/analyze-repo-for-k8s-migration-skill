import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis_pipeline import mcp_server
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

    def test_stdio_server_emits_korean_text_as_utf8(self):
        output = io.BytesIO()
        stdout = io.TextIOWrapper(output, encoding="cp949")
        with (
            patch.object(sys, "stdin", io.StringIO('{"jsonrpc":"2.0"}\n')),
            patch.object(sys, "stdout", stdout),
            patch.object(sys, "stderr", io.StringIO()),
            patch.object(mcp_server, "handle", return_value={"message": "Kubernetes 설계 입력 요약"}),
        ):
            mcp_server.main()

        self.assertIn("Kubernetes 설계 입력 요약", output.getvalue().decode("utf-8"))

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

    def test_submit_is_payload_only_and_payload_contract_is_transparent(self):
        tools = handle(Server(), {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]
        submit = next(tool for tool in tools if tool["name"] == "submit_discovery")
        schema = submit["inputSchema"]
        self.assertEqual(schema["required"], ["payload"])
        self.assertEqual(set(schema["properties"]), {"payload"})
        payload = schema["properties"]["payload"]
        self.assertFalse(payload["additionalProperties"])
        self.assertEqual(payload["properties"]["schema_version"], {"const": 1})
        self.assertEqual(payload["properties"]["stage"], {"const": "discovery"})
        self.assertEqual(
            set(payload["required"]),
            {"schema_version", "stage", "evidence", "claims", "rule_applications", "signals", "candidate_ids", "decisions"},
        )
        self.assertEqual(payload["properties"]["evidence"]["items"]["required"], ["alias", "observation_ref"])
        relationships = next(tool for tool in tools if tool["name"] == "submit_relationships")
        edge_schema = relationships["inputSchema"]["properties"]["payload"]["properties"]["graph_edges"]["items"]
        self.assertFalse(edge_schema["additionalProperties"])
        self.assertEqual(
            set(edge_schema["required"]),
            {
                "id", "source_process_id", "target_id", "target_kind", "dependency_type", "mechanism", "endpoint_name",
                "required_for_function", "startup_use", "management_boundary", "timing", "execution_location", "claim_ids", "status",
            },
        )
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
