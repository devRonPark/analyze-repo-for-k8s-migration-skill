from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch

from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types
from pydantic import PrivateAttr

from migration_assistant.adk_runner import parse_structured_final
from migration_assistant.analysis import AnalysisResult, analyze, render_report
from migration_assistant.cli import main
from migration_assistant.target import BudgetExceededError, SafetyBudget
from migration_assistant.adk_model import OpenAICompatibleAdkLlm
from migration_assistant.adk_tools import AdkRepositoryToolset, DuplicateTracker, ValidationLedger
from migration_assistant.config import Settings
from migration_assistant.repository_tools import RepositoryTools, RepositoryToolError
from migration_assistant.tool_protocol import RunControlLedger, ToolErrorCode, ToolIssue, error_envelope
from migration_assistant.tool_contract import PUBLIC_AGENT_TOOL_NAMES


class RepeatingToolLlm(BaseLlm):
    model: str = "fake-repeat-model"
    _calls: int = PrivateAttr(0)

    async def generate_content_async(self, llm_request, stream: bool = False):
        self._calls += 1
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            name="search_text",
                            args={"pattern": "PORT"},
                            id=f"repeat-{self._calls}",
                        )
                    )
                ],
            ),
            partial=False,
        )


class InvalidFinalLlm(BaseLlm):
    model: str = "fake-invalid-final-model"

    async def generate_content_async(self, llm_request, stream: bool = False):
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text="분석을 마쳤습니다.")]),
            partial=False,
        )


class ValidFinalLlm(BaseLlm):
    model: str = "fake-valid-final-model"

    async def generate_content_async(self, llm_request, stream: bool = False):
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        text='{"status":"complete","summary":"구조화된 최종 결과","evidence":[{"status":"confirmed","path":"app.py","line_start":1,"line_end":1,"text":"PORT = 8080"}],"iterations":1,"errors":[]}'
                    )
                ],
            ),
            partial=False,
        )


class RepositoryAwareValidFinalLlm(BaseLlm):
    model: str = "fake-repository-aware-final-model"

    async def generate_content_async(self, llm_request, stream: bool = False):
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        text='{"status":"complete","summary":"PORT 설정이 확인되었습니다.","evidence":[{"id":"e1","status":"confirmed","path":"app.py","line_start":1,"line_end":1,"claim":"PORT 설정이 확인됨","text":"PORT = 8080"}],"findings":[{"id":"f1","status":"confirmed","claim":"PORT 설정이 확인됨","evidence_ids":["e1"]}],"iterations":0,"errors":[],"termination":"normal"}'
                    )
                ],
            ),
            partial=False,
        )


class FalseRepositoryAwareFinalLlm(BaseLlm):
    model: str = "fake-false-repository-aware-final-model"

    async def generate_content_async(self, llm_request, stream: bool = False):
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        text='{"status":"complete","summary":"허위 근거","evidence":[{"id":"e1","status":"confirmed","path":"missing.py","line_start":99,"line_end":99,"claim":"PORT 설정이 확인됨","text":"PORT = 8080"}],"findings":[{"id":"f1","status":"confirmed","claim":"PORT 설정이 확인됨","evidence_ids":["e1"]}],"iterations":0,"errors":[],"termination":"normal"}'
                    )
                ],
            ),
            partial=False,
        )


class RecoveryValidationLlm(BaseLlm):
    model: str = "fake-recovery-validation-model"
    _calls: int = PrivateAttr(0)

    async def generate_content_async(self, llm_request, stream: bool = False):
        self._calls += 1
        if self._calls == 1:
            part = types.Part(
                function_call=types.FunctionCall(
                    name="read_file",
                    args={"relative": "."},
                    id="bad-read",
                )
            )
        else:
            part = types.Part(
                function_call=types.FunctionCall(
                    name="validate_analysis",
                    args={
                        "status": "complete",
                        "summary": "PORT 설정이 확인되었습니다.",
                        "evidence": [{
                            "id": "e1",
                            "status": "confirmed",
                            "path": "app.py",
                            "line_start": 1,
                            "line_end": 1,
                            "claim": "PORT 설정이 확인됨",
                            "text": "PORT = 8080",
                        }],
                        "findings": [{
                            "id": "f1",
                            "status": "confirmed",
                            "claim": "PORT 설정이 확인됨",
                            "evidence_ids": ["e1"],
                        }],
                        "iterations": 1,
                        "errors": [],
                        "termination": "normal",
                    },
                    id="valid-submit",
                )
            )
        yield LlmResponse(content=types.Content(role="model", parts=[part]), partial=False)


class ValidationRetryLlm(BaseLlm):
    model: str = "fake-validation-retry-model"
    _calls: int = PrivateAttr(0)

    async def generate_content_async(self, llm_request, stream: bool = False):
        self._calls += 1
        evidence = {
            "status": "confirmed",
            "path": "app.py",
            "line_start": 1,
            "line_end": 1,
            "claim": "PORT 설정이 확인됨",
            "text": "PORT = 8080",
        }
        if self._calls > 1:
            evidence["id"] = "e1"
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(function_call=types.FunctionCall(
                    name="validate_analysis",
                    args={
                        "status": "complete",
                        "summary": "PORT 설정이 확인되었습니다.",
                        "evidence": [evidence],
                        "findings": [{"id": "f1", "status": "confirmed", "claim": "PORT 설정이 확인됨", "evidence_ids": ["e1"]}],
                        "iterations": 1,
                        "errors": [],
                        "termination": "normal",
                    },
                    id=f"validation-{self._calls}",
                ))],
            ),
            partial=False,
        )


class Phase1ContractTests(unittest.TestCase):
    def make_repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
        (repo / "app.py").write_text("PORT = 8080\n", encoding="utf-8")
        return repo

    def test_tool_error_envelope_is_stable_and_actionable(self):
        issue = ToolIssue(
            code=ToolErrorCode.INVALID_ARGUMENTS,
            category="validation",
            message="line_end is invalid",
            field_path="$.line_end",
            retryable=True,
        )

        self.assertEqual(
            error_envelope(issue, allowed_next_actions=("read_file_lines", "validate_analysis")),
            {
                "ok": False,
                "data": None,
                "error": {
                    "code": "invalid_arguments",
                    "category": "validation",
                    "message": "line_end is invalid",
                    "field_path": "$.line_end",
                    "retryable": True,
                    "allowed_next_actions": ["read_file_lines", "validate_analysis"],
                },
                "meta": {},
            },
        )

    def test_partial_requires_positive_line_backed_evidence(self):
        with self.assertRaisesRegex(ValueError, "partial.*line-backed Evidence"):
            AnalysisResult.model_validate({
                "status": "partial",
                "summary": "일부 분석",
                "evidence": [],
                "findings": [],
                "iterations": 1,
                "errors": ["근거 부족"],
                "termination": "normal",
            })

    def test_duplicate_calls_without_grounded_evidence_end_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = analyze(
                self.make_repo(root),
                root / "output",
                adk_model=RepeatingToolLlm(),
                max_iterations=20,
            )
            self.assertEqual(result.status, "failed")
            self.assertTrue(any("no-progress" in error for error in result.errors))
            self.assertLess(result.iterations, 20)

    def test_invalid_final_response_is_structured_partial_not_uncaught(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = analyze(self.make_repo(root), root / "output", adk_model=InvalidFinalLlm(), max_iterations=3)
            self.assertEqual(result.status, "failed")
            self.assertTrue(any("파싱" in error for error in result.errors))

    def test_zero_tool_structured_final_without_repository_validation_cannot_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = analyze(self.make_repo(root), root / "output", adk_model=ValidFinalLlm(), max_iterations=3)
            self.assertNotEqual(result.status, "complete")

    def test_zero_tool_repository_aware_valid_candidate_can_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = analyze(self.make_repo(root), root / "output", adk_model=RepositoryAwareValidFinalLlm(), max_iterations=3)
            self.assertEqual(result.status, "complete")

    def test_zero_tool_false_path_line_or_excerpt_cannot_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = analyze(self.make_repo(root), root / "output", adk_model=FalseRepositoryAwareFinalLlm(), max_iterations=3)
            self.assertNotEqual(result.status, "complete")

    def test_tool_error_recovery_can_submit_a_valid_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = analyze(self.make_repo(root), root / "output", adk_model=RecoveryValidationLlm(), max_iterations=5)
            self.assertEqual(result.status, "complete")

    def test_validation_error_is_returned_to_agent_for_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = analyze(self.make_repo(root), root / "output", adk_model=ValidationRetryLlm(), max_iterations=5)
            self.assertEqual(result.status, "complete")

    def test_fallback_never_promotes_observation_to_confirmed_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze(self.make_repo(Path(tmp)), Path(tmp) / "output", adk_model=InvalidFinalLlm(), max_iterations=3)
            self.assertNotEqual(result.status, "complete")
            self.assertNotIn("confirmed", {item.status for item in result.evidence})

    def test_shared_redactor_covers_tool_output_history_exception_ledger_and_report(self):
        repository = RepositoryTools(Path.cwd(), budget=SafetyBudget())
        ledger = ValidationLedger()
        tracker = DuplicateTracker()
        toolset = AdkRepositoryToolset(repository, ledger, tracker)
        output = toolset._call("synthetic", {"url": "https://u:p@example.test"}, lambda: {"url": "https://u:p@example.test", "password": "pw"})
        self.assertNotIn("u:p", repr(output))
        duplicate = toolset._call("synthetic-duplicate", {"password": "pw"}, lambda: {"ok": True})
        duplicate = toolset._call("synthetic-duplicate", {"password": "pw"}, lambda: {"ok": True})
        self.assertNotIn("pw", repr(duplicate))
        error = toolset._call("synthetic-error", {}, lambda: (_ for _ in ()).throw(RepositoryToolError("jdbc://u:p@example.test?password=pw")))
        self.assertNotIn("u:p", repr(error))
        self.assertNotIn("pw", repr(ledger.tool_error))
        messages = OpenAICompatibleAdkLlm._messages(
            LlmRequest(contents=[types.Content(role="user", parts=[types.Part(text="jdbc://u:p@example.test?password=pw")])])
        )
        self.assertNotIn("u:p", repr(messages))
        self.assertNotIn("pw", repr(messages))
        report = render_report(AnalysisResult.model_validate({"status": "failed", "summary": "jdbc://u:p@example.test?password=pw", "errors": ["password=pw"]}))
        self.assertNotIn("u:p", report)
        self.assertNotIn("pw", report)

    def test_repository_tool_error_gives_a_specific_safe_recovery_action(self):
        repository = RepositoryTools(Path.cwd(), budget=SafetyBudget())
        toolset = AdkRepositoryToolset(repository, ValidationLedger(), DuplicateTracker())

        result = toolset.read_file(".git/config")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "forbidden_path")
        self.assertIn(".git", result["error"]["message"])
        self.assertEqual(result["error"]["allowed_next_actions"], ["validate_analysis"])

    def test_forbidden_glob_reports_the_actual_argument_field(self):
        toolset = AdkRepositoryToolset(
            RepositoryTools(Path.cwd(), budget=SafetyBudget()),
            ValidationLedger(),
            DuplicateTracker(),
        )

        result = toolset.find_files(".git/**")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "forbidden_path")
        self.assertEqual(result["error"]["field_path"], "$.pattern")

    def test_validation_failure_preserves_repository_error_for_recovery(self):
        repository = RepositoryTools(Path.cwd(), budget=SafetyBudget())
        ledger = ValidationLedger()
        toolset = AdkRepositoryToolset(repository, ledger, DuplicateTracker())

        result = toolset.validate_analysis(
            status="partial",
            summary="근거 부족",
            evidence=[{
                "id": "e1",
                "status": "confirmed",
                "path": "missing.py",
                "line_start": 1,
                "line_end": 1,
                "claim": "설정이 확인됨",
                "text": "PORT = 8080",
            }],
            findings=[],
            iterations=1,
            errors=["missing.py를 확인하지 못함"],
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "candidate_schema")
        self.assertIn("missing.py", result["error"]["message"])
        self.assertIn("missing.py", ledger.validation_error or "")

    def test_validation_schema_error_explains_top_level_status_values(self):
        repository = RepositoryTools(Path.cwd(), budget=SafetyBudget())
        toolset = AdkRepositoryToolset(repository, ValidationLedger(), DuplicateTracker())

        result = toolset.validate_analysis(
            status="confirmed",
            summary="잘못된 top-level status",
            evidence=[],
            findings=[],
            iterations=1,
            errors=[],
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "candidate_schema")
        self.assertEqual(result["error"]["allowed_next_actions"], ["validate_analysis"])

    def test_validation_normalizes_a_verified_line_excerpt_before_schema_commit(self):
        repository = RepositoryTools(Path.cwd(), budget=SafetyBudget())
        ledger = ValidationLedger()
        toolset = AdkRepositoryToolset(repository, ledger, DuplicateTracker())

        result = toolset.validate_analysis(
            status="complete",
            summary="검증된 결과",
            evidence=[{
                "id": "e1",
                "status": "confirmed",
                "path": "migration_assistant/target.py",
                "line_start": 1,
                "line_end": 1,
                "claim": "target 경계가 확인됨",
                "text": "잘못된 복사본",
            }],
            findings=[{"id": "f1", "status": "confirmed", "claim": "target 경계가 확인됨", "evidence_ids": ["e1"]}],
            iterations=1,
            errors=[],
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["meta"]["terminal"])
        self.assertEqual(ledger.result.evidence[0].text, '"""Deterministic read-only target and output safety boundary."""')

    def test_validation_repairs_missing_structural_ids_from_verified_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            ledger = ValidationLedger()
            toolset = AdkRepositoryToolset(RepositoryTools(repo), ledger, DuplicateTracker())
            result = toolset.validate_analysis(
                status="complete",
                summary="검증된 결과",
                evidence=[{
                    "status": "confirmed",
                    "path": "app.py",
                    "line_start": 1,
                    "line_end": 1,
                    "claim": "PORT 설정이 확인됨",
                    "text": "placeholder",
                }],
                findings=[{"status": "confirmed", "claim": "PORT 설정이 확인됨"}],
                iterations=1,
                errors=[],
            )

            self.assertTrue(result["ok"], result)
            self.assertEqual(ledger.result.evidence[0].id, "e1")
            self.assertEqual(ledger.result.findings[0].evidence_ids, ["e1"])

    def test_validation_recovers_an_omitted_top_level_status_after_grounding(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            ledger = ValidationLedger()
            toolset = AdkRepositoryToolset(RepositoryTools(repo), ledger, DuplicateTracker())
            result = toolset.validate_analysis(
                status="",
                summary="검증된 결과",
                evidence=[{
                    "status": "confirmed",
                    "path": "app.py",
                    "line_start": 1,
                    "line_end": 1,
                    "claim": "PORT 설정이 확인됨",
                    "text": "PORT = 8080",
                }],
                findings=[{"status": "confirmed", "claim": "PORT 설정이 확인됨"}],
                iterations=1,
                errors=[],
            )

            self.assertTrue(result["ok"], result)
            self.assertEqual(ledger.result.status, "complete")

    def test_fenced_structured_result_is_safely_extractable(self):
        self.assertEqual(
            parse_structured_final("```json\n{\"status\": \"partial\"}\n```"),
            {"status": "partial"},
        )
        self.assertIsNone(parse_structured_final("일반 문장만 반환"))
        self.assertEqual(
            parse_structured_final("완료했습니다. {\"status\": \"partial\", \"summary\": \"근거 부족\"}"),
            {"status": "partial", "summary": "근거 부족"},
        )

    def test_malformed_raw_arguments_are_not_replaced_with_empty_object(self):
        response = OpenAICompatibleAdkLlm._response(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": '{"relative":"broken',
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        )

        self.assertEqual(response.content.parts[0].text, "Tool protocol validation failed.")
        self.assertEqual(response.custom_metadata["protocol_issue"]["code"], "malformed_arguments")
        self.assertFalse(any(part.function_call for part in response.content.parts))

    def test_after_model_callback_blocks_unknown_name_before_adk_dispatch(self):
        control = RunControlLedger()
        toolset = AdkRepositoryToolset(
            RepositoryTools(Path.cwd(), budget=SafetyBudget()),
            ValidationLedger(),
            DuplicateTracker(),
            control=control,
        )
        response = LlmResponse(content=types.Content(
            role="model",
            parts=[types.Part(function_call=types.FunctionCall(name="shell", args={}, id="bad"))],
        ))

        replaced = toolset.after_model_callback(None, response)

        self.assertEqual(control.protocol_issue.code, ToolErrorCode.INVALID_TOOL_NAME)
        self.assertFalse(any(part.function_call for part in replaced.content.parts))

    def test_closed_alias_is_canonicalized_but_embedded_json_suffix_is_rejected(self):
        control = RunControlLedger()
        toolset = AdkRepositoryToolset(
            RepositoryTools(Path.cwd(), budget=SafetyBudget()),
            ValidationLedger(),
            DuplicateTracker(),
            control=control,
        )
        accepted = toolset.after_model_callback(None, LlmResponse(content=types.Content(
            role="model",
            parts=[types.Part(function_call=types.FunctionCall(
                name="read_filearg", args={"relative": "migration_assistant/agent.py"}, id="alias",
            ))],
        )))
        self.assertEqual(accepted.content.parts[0].function_call.name, "read_file")

        rejected = toolset.after_model_callback(None, LlmResponse(content=types.Content(
            role="model",
            parts=[types.Part(function_call=types.FunctionCall(
                name='read_fileargs{"relative":"app.py"}', args={}, id="embedded",
            ))],
        )))
        self.assertEqual(control.protocol_issue.code, ToolErrorCode.INVALID_TOOL_NAME)
        self.assertFalse(any(part.function_call for part in rejected.content.parts))

    def test_adk_model_consumes_the_shared_iteration_budget(self):
        model = OpenAICompatibleAdkLlm(Settings(), budget=SafetyBudget(max_iterations=1))
        request = types.Content(role="user", parts=[types.Part(text="hello")])

        async def collect():
            async for _ in model.generate_content_async(
                LlmRequest(contents=[request])
            ):
                pass

        with patch.object(model._adapter, "complete", return_value={"choices": [{"message": {"content": "ok"}}]}):
            import asyncio

            asyncio.run(collect())
            with self.assertRaises(BudgetExceededError):
                asyncio.run(collect())

    def test_adk_messages_preserve_assistant_calls_and_tool_responses(self):
        request = LlmRequest(
            contents=[
                types.Content(
                    role="model",
                    parts=[
                        types.Part(function_call=types.FunctionCall(name="read_file", args={"relative": "app.py"}, id="c1")),
                        types.Part(text="관찰을 수행합니다."),
                    ],
                ),
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                name="read_file", id="c1", response={"path": "app.py", "binary": False}
                            )
                        )
                    ],
                ),
            ]
        )
        messages = OpenAICompatibleAdkLlm._messages(request)
        self.assertEqual(messages[0]["role"], "assistant")
        self.assertIn("tool_calls", messages[0])
        self.assertEqual(messages[1]["role"], "tool")
        self.assertEqual(messages[1]["tool_call_id"], "c1")

    def test_adk_messages_heal_missing_tool_response_without_fabricating_observation(self):
        request = LlmRequest(
            contents=[
                types.Content(
                    role="model",
                    parts=[types.Part(function_call=types.FunctionCall(name="read_file", args={}, id="missing-1"))],
                ),
                types.Content(role="user", parts=[types.Part(text="continue")]),
            ]
        )
        messages = OpenAICompatibleAdkLlm._messages(request)
        self.assertEqual(messages[1]["role"], "tool")
        missing = json.loads(messages[1]["content"])
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["error"]["code"], "malformed_arguments")
        self.assertFalse(missing["meta"]["executed"])

    def test_real_adk_function_declarations_become_openai_json_schema(self):
        repository = RepositoryTools(Path.cwd(), budget=SafetyBudget())
        toolset = AdkRepositoryToolset(repository, ValidationLedger(), DuplicateTracker())
        declarations = [tool._get_declaration() for tool in toolset.functions()]
        request = LlmRequest(config=types.GenerateContentConfig(tools=[types.Tool(function_declarations=declarations)]))
        wire_tools = OpenAICompatibleAdkLlm._tools(request)
        validate = next(item for item in wire_tools if item["function"]["name"] == "validate_analysis")
        schema = validate["function"]["parameters"]
        self.assertEqual(schema["type"], "object")
        self.assertEqual(set(schema["required"]), {"status", "summary", "evidence", "findings", "iterations", "errors"})
        evidence_items = schema["properties"]["evidence"]["items"]
        evidence_schema = schema["$defs"][evidence_items["$ref"].removeprefix("#/$defs/")]
        self.assertEqual(
            evidence_schema["properties"]["status"]["enum"],
            ["confirmed", "inferred", "unresolved", "conflicting"],
        )
        self.assertFalse(evidence_schema["additionalProperties"])
        self.assertNotIn("nullable", str(wire_tools))
        self.assertNotIn("propertyOrdering", str(wire_tools))

    def test_public_tool_descriptions_are_llm_readable(self):
        toolset = AdkRepositoryToolset(
            RepositoryTools(Path.cwd(), budget=SafetyBudget()),
            ValidationLedger(),
            DuplicateTracker(),
        )
        by_name = {tool.name: tool for tool in toolset.functions()}

        self.assertEqual(tuple(by_name), PUBLIC_AGENT_TOOL_NAMES)
        self.assertIn("Use when", by_name["search_text"].description)
        self.assertIn("Do not use when", by_name["search_text"].description)
        self.assertIn("Python regular expression", by_name["search_text"].description)
        self.assertIn("glob", by_name["find_files"].description)
        self.assertIn("On error", by_name["read_file_lines"].description)
        self.assertIn("Next action", by_name["validate_analysis"].description)
        for name in ("list_tree", "find_files", "search_text", "read_file", "read_file_lines"):
            self.assertIn("AGENTS.md", by_name[name].description)
            self.assertIn(".git", by_name[name].description)

    def test_invalid_tool_arguments_are_rejected_before_repository_operation(self):
        repository = RepositoryTools(Path.cwd(), budget=SafetyBudget())
        toolset = AdkRepositoryToolset(repository, ValidationLedger(), DuplicateTracker())
        read_lines = next(tool for tool in toolset.functions() if tool.name == "read_file_lines")

        with patch.object(repository, "read_file_lines", wraps=repository.read_file_lines) as operation:
            invalid_start = asyncio.run(read_lines.run_async(
                args={"relative": "app.py", "line_start": 0, "line_end": 1}, tool_context=None,
            ))
            reversed_range = asyncio.run(read_lines.run_async(
                args={"relative": "app.py", "line_start": 2, "line_end": 1}, tool_context=None,
            ))
            oversized_range = asyncio.run(read_lines.run_async(
                args={"relative": "app.py", "line_start": 1, "line_end": 5}, tool_context=None,
            ))

        self.assertFalse(invalid_start["ok"])
        self.assertEqual(invalid_start["error"]["code"], "invalid_arguments")
        self.assertEqual(invalid_start["error"]["field_path"], "$.line_start")
        self.assertEqual(reversed_range["error"]["field_path"], "$.line_end")
        self.assertEqual(oversized_range["error"]["field_path"], "$.line_end")
        operation.assert_not_called()

    def test_cli_maps_complete_partial_and_internal_failure(self):
        evidence = [{"id": "e1", "status": "confirmed", "path": "app.py", "line_start": 1, "line_end": 1, "claim": "PORT 설정", "text": "PORT = 8080"}]
        findings = [{"id": "f1", "status": "confirmed", "claim": "PORT 설정", "evidence_ids": ["e1"]}]
        complete = AnalysisResult.model_validate({"status": "complete", "summary": "ok", "evidence": evidence, "findings": findings})
        partial = AnalysisResult.model_validate({"status": "partial", "summary": "partial", "evidence": evidence, "errors": ["budget partial"]})
        with patch("migration_assistant.cli.analyze", return_value=complete):
            self.assertEqual(main(["analyze", "repo"]), 0)
        with patch("migration_assistant.cli.analyze", return_value=partial):
            self.assertEqual(main(["analyze", "repo"]), 2)
        with patch("migration_assistant.cli.analyze", side_effect=RuntimeError("internal")):
            self.assertEqual(main(["analyze", "repo"]), 1)
        failed = AnalysisResult.model_validate({"status": "failed", "summary": "failed", "evidence": []})
        with patch("migration_assistant.cli.analyze", return_value=failed):
            self.assertEqual(main(["analyze", "repo"]), 1)


if __name__ == "__main__":
    unittest.main()
