from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from google.adk.models import LlmResponse
from google.genai import types

from devtools.run_phase1_live_acceptance import AcceptanceRun, _is_success
from migration_assistant.adk_model import OpenAICompatibleAdkLlm
from migration_assistant.adk_runner import _recovery_prompt
from migration_assistant.adk_tools import AdkRepositoryToolset, DuplicateTracker, ValidationLedger
from migration_assistant.exploration_ledger import ExplorationLedger
from migration_assistant.repository_tools import RepositoryTools
from migration_assistant.target import SafetyBudget
from migration_assistant.tool_protocol import RunControlLedger, RunPhase, ToolErrorCode, ToolIssue


class AdkRecoveryContractTests(unittest.TestCase):
    def make_repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
        (repo / "app.py").write_text("PORT = 8080\n", encoding="utf-8")
        return repo

    def toolset(self, repo: Path, control: RunControlLedger | None = None) -> AdkRepositoryToolset:
        return AdkRepositoryToolset(
            RepositoryTools(repo, budget=SafetyBudget(max_iterations=10)),
            ValidationLedger(),
            DuplicateTracker(),
            control=control,
        )

    def candidate(self, excerpt: str) -> dict[str, object]:
        return {
            "status": "partial",
            "summary": "PORT 설정을 확인했습니다.",
            "evidence": [{
                "id": "e1",
                "status": "confirmed",
                "path": "app.py",
                "line_start": 1,
                "line_end": 1,
                "claim": "PORT 설정이 확인됨",
                "text": excerpt,
            }],
            "findings": [{
                "id": "f1",
                "status": "confirmed",
                "claim": "PORT 설정이 확인됨",
                "evidence_ids": ["e1"],
            }],
            "iterations": 1,
            "errors": ["추가 배포 선택은 미확인"],
            "termination": "normal",
            "components": [],
        }

    def test_grounding_recovery_observes_before_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            control = RunControlLedger(phase=RunPhase.GROUND)
            toolset = self.toolset(repo, control)
            invalid = self.candidate("wrong excerpt")
            first = toolset.validate_analysis(**invalid)

            self.assertEqual(first["error"]["code"], "evidence_grounding")
            self.assertIn("read_file_lines", first["error"]["allowed_next_actions"])
            self.assertNotEqual(first["error"]["allowed_next_actions"], ["validate_analysis"])

            read_lines = next(tool for tool in toolset.functions() if tool.name == "read_file_lines")
            self.assertIsNone(toolset.before_tool_callback(read_lines, {
                "relative": "app.py", "line_start": 1, "line_end": 1,
            }, None))
            observation = toolset.read_file_lines("app.py", 1, 1)
            self.assertEqual(observation["data"][0]["text"], "PORT = 8080")
            self.assertEqual(control.allowed_next_actions(tuple(tool.name for tool in toolset.functions())), ("validate_analysis",))

            validate = next(tool for tool in toolset.functions() if tool.name == "validate_analysis")
            corrected = self.candidate("PORT = 8080")
            self.assertIsNone(toolset.before_tool_callback(validate, corrected, None))
            accepted = toolset.validate_analysis(**corrected)

            self.assertTrue(accepted["ok"])
            self.assertEqual(toolset.tracker.signatures.__len__(), 3)
            self.assertEqual(control.inline_corrections, 1)
            self.assertEqual(control.validation_attempts, 2)

    def test_grounding_phase_violation_stops_and_keeps_original_issue_in_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            control = RunControlLedger(phase=RunPhase.GROUND)
            toolset = self.toolset(repo, control)
            invalid = self.candidate("wrong excerpt")
            grounding = toolset.validate_analysis(**invalid)
            validate = next(tool for tool in toolset.functions() if tool.name == "validate_analysis")

            rejected = toolset.before_tool_callback(validate, invalid, None)

            self.assertEqual(grounding["error"]["code"], "evidence_grounding")
            self.assertEqual(rejected["error"]["code"], "invalid_arguments")
            self.assertEqual(rejected["error"]["category"], "state")
            self.assertEqual(rejected["error"]["field_path"], "$.name")
            self.assertEqual(rejected["error"]["allowed_next_actions"], [])
            self.assertTrue(control.stop_requested)
            self.assertEqual(control.protocol_issue.code, ToolErrorCode.INVALID_ARGUMENTS)
            self.assertEqual(control.audit_issues[-1].code, ToolErrorCode.EVIDENCE_GROUNDING)
            self.assertEqual(control.validation_attempts, 1)

    def test_grounding_phase_error_precedes_invalid_candidate_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            control = RunControlLedger(phase=RunPhase.GROUND)
            toolset = self.toolset(repo, control)
            invalid = self.candidate("wrong excerpt")
            toolset.validate_analysis(**invalid)
            validate = next(tool for tool in toolset.functions() if tool.name == "validate_analysis")
            invalid["status"] = "bad"

            rejected = toolset.before_tool_callback(validate, invalid, None)

            self.assertEqual(rejected["error"]["code"], "invalid_arguments")
            self.assertEqual(rejected["error"]["category"], "state")
            self.assertEqual(rejected["error"]["field_path"], "$.name")
            self.assertEqual(rejected["error"]["allowed_next_actions"], [])
            self.assertTrue(control.stop_requested)
            self.assertEqual(control.validation_attempts, 1)

    def test_prebinding_candidate_schema_is_counted_without_handler_validation(self):
        control = RunControlLedger(phase=RunPhase.GROUND)
        toolset = self.toolset(Path.cwd(), control)
        validate = next(tool for tool in toolset.functions() if tool.name == "validate_analysis")

        first = toolset.before_tool_callback(validate, {"status": "잘못된 값"}, None)
        second = toolset.before_tool_callback(validate, {"status": "잘못된 값"}, None)

        self.assertEqual(first["error"]["code"], "candidate_schema")
        self.assertEqual(second["error"]["allowed_next_actions"], [])
        self.assertEqual(control.prebinding_rejections, 1)
        self.assertEqual(control.validation_attempts, 0)
        self.assertTrue(control.stop_requested)

    def test_validate_runtime_error_is_execution_error_not_candidate_schema(self):
        control = RunControlLedger(phase=RunPhase.GROUND)
        toolset = self.toolset(Path.cwd(), control)
        validate = next(tool for tool in toolset.functions() if tool.name == "validate_analysis")

        result = toolset.on_tool_error_callback(
            validate,
            {"status": "complete"},
            None,
            RuntimeError("password=do-not-leak"),
        )

        self.assertEqual(result["error"]["code"], "invalid_arguments")
        self.assertEqual(result["error"]["category"], "execution")
        self.assertFalse(result["error"]["retryable"])
        self.assertEqual(result["error"]["allowed_next_actions"], [])
        self.assertTrue(control.stop_requested)
        self.assertEqual(control.prebinding_rejections, 0)
        self.assertNotIn("do-not-leak", repr(result))

    def test_validate_internal_runtime_error_returns_bounded_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))

            class RaisingRepositoryTools(RepositoryTools):
                def validate_analysis(self, analysis):
                    raise RuntimeError("token=do-not-leak")

            repository = RaisingRepositoryTools(repo, budget=SafetyBudget(max_iterations=10))
            control = RunControlLedger(phase=RunPhase.GROUND)
            toolset = AdkRepositoryToolset(repository, ValidationLedger(), DuplicateTracker(), control=control)
            result = toolset.validate_analysis(**self.candidate("PORT = 8080"))

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["category"], "execution")
        self.assertFalse(result["error"]["retryable"])
        self.assertEqual(result["error"]["allowed_next_actions"], [])
        self.assertTrue(control.stop_requested)
        self.assertNotIn("do-not-leak", repr(result))

    def test_before_tool_callback_is_idempotent_for_same_delivery(self):
        control = RunControlLedger(phase=RunPhase.GROUND)
        toolset = self.toolset(Path.cwd(), control)
        validate = next(tool for tool in toolset.functions() if tool.name == "validate_analysis")
        control.record_issue(
            ToolIssue(
                code=ToolErrorCode.CANDIDATE_SCHEMA,
                category="validation",
                message="candidate 수정이 필요합니다.",
                retryable=True,
            ),
            allowed_next_actions=("validate_analysis",),
            originating_tool="validate_analysis",
            call_id="call-1",
        )

        class ToolContext:
            invocation_id = "invocation-1"
            function_call_id = "call-1"

        args = {
            "status": "complete",
            "summary": "password=do-not-leak",
            "evidence": [],
            "findings": [],
            "iterations": 0,
            "errors": [],
        }
        first = toolset.before_tool_callback(validate, args, ToolContext())
        second = toolset.before_tool_callback(validate, args, ToolContext())

        self.assertIsNone(first)
        self.assertIsNone(second)
        self.assertEqual(control.inline_corrections, 1)
        self.assertFalse(control.stop_requested)
        self.assertEqual(len(toolset.ledger.callback_telemetry), 1)
        telemetry = toolset.ledger.callback_telemetry[0]
        self.assertEqual(telemetry["callback_stage"], "before_tool")
        self.assertEqual(telemetry["tool_name"], "validate_analysis")
        self.assertEqual(telemetry["invocation_id"], "invocation-1")
        self.assertNotIn("do-not-leak", repr(telemetry))
        self.assertNotIn("args", telemetry)

    def test_adapter_malformed_arguments_keep_call_linkage(self):
        response = OpenAICompatibleAdkLlm._response(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {"name": "read_file", "arguments": '{"relative":"broken'},
                                }
                            ]
                        }
                    }
                ]
            }
        )

        call = next(part.function_call for part in response.content.parts if part.function_call)
        self.assertEqual((call.id, call.name), ("call-1", "read_file"))
        self.assertEqual(response.custom_metadata["call_linkage"], {"id": "call-1", "name": "read_file"})
        self.assertNotIn("broken", json.dumps(response.custom_metadata, ensure_ascii=False))

    def test_acceptance_gate_rejects_unobserved_or_over_cap_telemetry(self):
        def make(**overrides: object) -> AcceptanceRun:
            values: dict[str, object] = {
                "output_path": Path("output"),
                "exit_code": 0,
                "status": "complete",
                "terminal": True,
                "tool_calls": ("inspect_target", "validate_analysis"),
                "evidence_count": 1,
                "positive_evidence_count": 1,
                "protocol_error_codes": (),
                "telemetry_valid": True,
                "recovery_cap": 1,
                "validation_cap": 2,
                "prebinding_cap": 1,
                "inline_correction_cap": 3,
                "no_progress_cap": 3,
            }
            values.update(overrides)
            return AcceptanceRun(**values)

        self.assertTrue(_is_success(make()))
        self.assertFalse(_is_success(make(evidence_provenance=({"id": "e1", "sources": []},))))
        self.assertFalse(_is_success(make(validation_attempts=3)))
        self.assertFalse(_is_success(make(telemetry_valid=False)))


class RecoveryPromptCoverageProjectionTests(unittest.TestCase):
    """Task 2A: the recovery message is one of the few places adk_runner.py
    builds a message directly, so the coverage projection must reach it."""

    def test_recovery_prompt_without_a_ledger_has_no_coverage_reminder(self):
        control = RunControlLedger()
        prompt = _recovery_prompt(control, 1, ("inspect_target",))
        self.assertNotIn("required 질문", prompt)

    def test_recovery_prompt_names_unobserved_required_questions(self):
        control = RunControlLedger()
        ledger = ExplorationLedger()
        prompt = _recovery_prompt(control, 1, ("inspect_target",), ledger)
        self.assertIn("production_startup", prompt)
        self.assertIn("required 질문", prompt)

    def test_recovery_prompt_coverage_reminder_shrinks_as_questions_are_observed(self):
        control = RunControlLedger()
        ledger = ExplorationLedger()
        ledger.record_observation("production_startup", "search_text", "Dockerfile", 1, 1)
        prompt = _recovery_prompt(control, 1, ("inspect_target",), ledger)
        self.assertNotIn("production_startup", prompt)

    def test_recovery_prompt_coverage_reminder_carries_no_path_or_value(self):
        control = RunControlLedger()
        ledger = ExplorationLedger()
        ledger.record_observation("runtime_config_and_secret_names", "read_file_lines", "config/application.yml", 1, 1)
        prompt = _recovery_prompt(control, 1, ("inspect_target",), ledger)
        self.assertNotIn("application.yml", prompt)


if __name__ == "__main__":
    unittest.main()
