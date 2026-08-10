import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from runtime.python.tests.test_contracts_stage import ContractsStageTests
from analysis_pipeline.mcp_server import handle


class FinalizationStageTests(unittest.TestCase):
    def complete_contracts(self, mode: str) -> tuple[object, object, dict]:
        helper = ContractsStageTests()
        temporary, server, boundaries = helper.start_with_boundaries(mode)
        contracts, failed = server.tool_call(
            "submit_contracts",
            {"payload": helper.payload(boundaries, mode)},
        )
        self.assertFalse(failed, contracts)
        return temporary, server, contracts

    def test_finalizes_the_accepted_five_stage_state_without_mutating_target(self) -> None:
        for mode, heading in (("summary", "# Kubernetes 설계 입력 요약"), ("detailed", "# Kubernetes 설계 입력 상세 평가")):
            with self.subTest(mode=mode):
                temporary, server, contracts = self.complete_contracts(mode)
                with temporary:
                    target_root = server.session.target_root
                    before = subprocess.run(
                        ["git", "-C", str(target_root), "status", "--short"],
                        check=True,
                        capture_output=True,
                        text=True,
                    ).stdout
                    result, failed = server.tool_call("finalize_analysis", {})
                    after = subprocess.run(
                        ["git", "-C", str(target_root), "status", "--short"],
                        check=True,
                        capture_output=True,
                        text=True,
                    ).stdout

                self.assertFalse(failed, result)
                self.assertEqual(before, after)
                self.assertEqual(result["status"], "finalized")
                self.assertEqual(result["mode"], mode)
                self.assertTrue(result["markdown"].startswith(heading))
                self.assertIn("app.py:1-1", result["markdown"])
                self.assertNotIn("print('ready')", result["markdown"])
                self.assertIsNotNone(server.state)

    def test_final_report_satisfies_the_existing_markdown_contract(self) -> None:
        for mode in ("summary", "detailed"):
            with self.subTest(mode=mode):
                temporary, server, contracts = self.complete_contracts(mode)
                with temporary:
                    result, failed = server.tool_call("finalize_analysis", {})
                self.assertFalse(failed, result)
                with tempfile.TemporaryDirectory() as directory:
                    report = f"{directory}/report.md"
                    with open(report, "w", encoding="utf-8") as handle:
                        handle.write(result["markdown"])
                    validation = subprocess.run(
                        [sys.executable, "scripts/validate_report.py", report, "--mode", mode],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                self.assertEqual(validation.returncode, 0, validation.stdout + validation.stderr)

    def test_render_failure_preserves_the_active_finalization_state(self) -> None:
        temporary, server, contracts = self.complete_contracts("summary")
        with temporary, patch("analysis_pipeline.session.project_and_render", side_effect=ValueError("render failed")):
            result, failed = server.tool_call("finalize_analysis", {})

        self.assertTrue(failed)
        self.assertEqual(result["code"], "render failed")
        self.assertEqual(server.session.current_stage, "finalize")
        self.assertEqual(server.session.revision, contracts["revision"])

    def test_successful_cleanup_rejects_repeat_finalization_and_allows_a_new_start(self) -> None:
        temporary, server, contracts = self.complete_contracts("summary")
        with temporary:
            target_root = server.session.target_root
            final_response = handle(server, {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {"name": "finalize_analysis", "arguments": {}},
            })
            repeated, repeated_failed = server.tool_call("finalize_analysis", {})
            restarted, restart_failed = server.tool_call("start_analysis", {"target_path": str(target_root), "mode": "summary"})

        self.assertIn("result", final_response)
        self.assertTrue(repeated_failed)
        self.assertEqual(repeated["code"], "analysis_not_started")
        self.assertFalse(restart_failed, restarted)

    def test_mcp_finalization_exposes_only_markdown_content_and_closed_metadata(self) -> None:
        temporary, server, contracts = self.complete_contracts("summary")
        with temporary:
            response = handle(server, {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {"name": "finalize_analysis", "arguments": {}},
            })

        result = response["result"]
        self.assertTrue(result["content"][0]["text"].startswith("# Kubernetes 설계 입력 요약"))
        self.assertEqual(set(result["structuredContent"]), {"status", "analysis_id", "mode", "revision"})
        self.assertEqual(result["structuredContent"]["status"], "finalized")
        self.assertIsNone(server.state)

    def test_mcp_response_construction_failure_preserves_the_active_finalization_state(self) -> None:
        temporary, server, contracts = self.complete_contracts("summary")
        with temporary, patch("analysis_pipeline.mcp_server.markdown_result", side_effect=ValueError("transport failed")):
            response = handle(server, {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {"name": "finalize_analysis", "arguments": {}},
            })

        self.assertTrue(response["result"]["isError"])
        self.assertEqual(server.session.current_stage, "finalize")
        self.assertEqual(server.session.revision, contracts["revision"])

    def test_unknown_report_slot_uses_its_actual_tool_issued_absence_descriptor(self) -> None:
        helper = ContractsStageTests()
        temporary, server, boundaries = helper.start_with_boundaries("summary")
        with temporary:
            absence = server.session.registry.issue_absence("contracts", "config", "*.yaml", "DATABASE_URL")
            payload = helper.payload(boundaries, "summary")
            credential_claim = next(claim for claim in payload["claims"] if claim["id"] == "claim-credential_exposure")
            payload["evidence"].append({"alias": "absence", "observation_ref": absence["observation_ref"]})
            credential_claim.update({
                "status": "unknown",
                "scope": "config",
                "blocked_decision": "credential_exposure",
                "evidence_aliases": ["slot-credential_exposure", "absence"],
            })
            credential_slot = next(slot for slot in payload["report_slots"] if slot["id"] == "credential_exposure")
            credential_slot["status"] = "unknown"
            contracts, failed = server.tool_call(
                "submit_contracts", {"payload": payload}
            )
            self.assertFalse(failed, contracts)
            result, failed = server.tool_call("finalize_analysis", {})

        self.assertFalse(failed, result)
        self.assertIn("검색(scope=config, pattern=DATABASE_URL, result=없음)", result["markdown"])


if __name__ == "__main__":
    unittest.main()
