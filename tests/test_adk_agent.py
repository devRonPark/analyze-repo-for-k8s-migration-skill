from __future__ import annotations

import inspect
import subprocess
import tempfile
import unittest
from pathlib import Path

from google.adk.models import BaseLlm, LlmResponse
from google.genai import types
from pydantic import PrivateAttr

from migration_assistant.analysis import AnalysisResult, analyze
from migration_assistant.agent import AgentApplication, PUBLIC_AGENT_TOOL_NAMES, build_migration_instruction, create_agent
from migration_assistant.adk_tools import DuplicateTracker, ValidationLedger
from migration_assistant.config import Settings
from migration_assistant.exploration_policy import DEFAULT_MIGRATION_POLICY
from migration_assistant.repository_tools import RepositoryTools
from migration_assistant.target import SafetyBudget
from migration_assistant.tool_protocol import RunControlLedger


class ScriptedAdkLlm(BaseLlm):
    """A deterministic ADK model used only to exercise the real Runner path."""

    model: str = "fake-test-model"
    _calls: int = PrivateAttr(0)
    _tool_names: list[str] = PrivateAttr(default_factory=list)

    async def generate_content_async(self, llm_request, stream: bool = False):
        self._calls += 1
        if self._calls == 1:
            name = "inspect_target"
            args = {}
        elif self._calls == 2:
            name = "search_text"
            args = {"pattern": "PORT"}
        elif self._calls == 3:
            name = "validate_analysis"
            args = {
                "status": "complete",
                "summary": "Agent가 Repository 근거를 종합했습니다.",
                "evidence": [
                    {"id": "e1", "status": "confirmed", "path": "app.py", "line_start": 1, "line_end": 1, "claim": "PORT 설정", "text": "PORT = 8080"},
                    {"id": "e2", "status": "inferred", "path": "app.py", "line_start": 1, "line_end": 1, "claim": "PORT 설정 추정", "text": "PORT = 8080"},
                    {"id": "e3", "status": "conflicting", "path": "app.py", "line_start": 1, "line_end": 1, "claim": "PORT 설정 상충", "text": "PORT = 8080"},
                    {"id": "e4", "status": "unresolved", "absence_scope": "**/*.yaml", "absence_pattern": "ingress", "result": "not searched"},
                ],
                "findings": [
                    {"id": "f1", "status": "confirmed", "claim": "PORT 설정", "evidence_ids": ["e1"]},
                    {"id": "f2", "status": "inferred", "claim": "PORT 설정 추정", "evidence_ids": ["e2"]},
                    {"id": "f3", "status": "conflicting", "claim": "PORT 설정 상충", "evidence_ids": ["e3"]},
                    {"id": "f4", "status": "unresolved", "claim": "Ingress는 미확인", "evidence_ids": ["e4"], "resolution_owner": "repository", "resolution_source": "검색 범위", "reason": "not searched"},
                ],
                "iterations": 2,
                "errors": [],
                "termination": "normal",
            }
        else:
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text='{"status":"complete","summary":"Agent가 검증된 분석을 완료했습니다."}')],
                ),
                partial=False,
            )
            return
        self._tool_names.append(name)
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(function_call=types.FunctionCall(name=name, args=args, id=f"call-{self._calls}"))],
            ),
            partial=False,
        )


class AdkAgentTests(unittest.TestCase):
    def make_repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
        (repo / "app.py").write_text("PORT = 8080\n", encoding="utf-8")
        return repo

    def test_agent_registers_exactly_eight_tools_and_uses_adk_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root)
            model = ScriptedAdkLlm()
            application = create_agent()
            agent = application.build_root_agent(
                repository_tools=RepositoryTools(repo, budget=SafetyBudget()),
                ledger=ValidationLedger(),
                tracker=DuplicateTracker(),
                budget=SafetyBudget(),
                model_override=model,
            )

            self.assertEqual(
                tuple(tool.__name__ if hasattr(tool, "__name__") else tool.name for tool in agent.tools),
                PUBLIC_AGENT_TOOL_NAMES,
            )
            self.assertEqual(type(agent.model), ScriptedAdkLlm)
            self.assertIsNotNone(agent.after_model_callback)
            self.assertIsNotNone(agent.before_tool_callback)
            self.assertIsNotNone(agent.after_tool_callback)
            self.assertIsNotNone(agent.on_tool_error_callback)

    def test_agent_instruction_bounds_line_evidence_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            agent = create_agent().build_root_agent(
                repository_tools=RepositoryTools(repo, budget=SafetyBudget()),
                ledger=ValidationLedger(),
                tracker=DuplicateTracker(),
                budget=SafetyBudget(),
                model_override=ScriptedAdkLlm(),
            )

            self.assertIn("최대 10줄", agent.instruction)
            self.assertIn("search_text hit", agent.instruction)
            self.assertIn("ok=true", agent.instruction)
            self.assertIn("meta.terminal=true", agent.instruction)
            self.assertNotIn("valid=true", agent.instruction)
            self.assertIn(", ".join(PUBLIC_AGENT_TOOL_NAMES), agent.instruction)
            self.assertIn("이 8개 외 Tool을 만들거나 호출하지 마세요", agent.instruction)

    def test_agent_instruction_shows_nested_component_field_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            agent = create_agent().build_root_agent(
                repository_tools=RepositoryTools(repo, budget=SafetyBudget()),
                ledger=ValidationLedger(),
                tracker=DuplicateTracker(),
                budget=SafetyBudget(),
                model_override=ScriptedAdkLlm(),
            )

            for instruction in (
                "production_startup도 문자열이 아니라 FieldValue 객체",
                "ports=[{container_port={status='confirmed', value=8080, evidence_ids=['e1']}}]",
                "container_image={reference={status='confirmed', value='repo/image:tag', evidence_ids=['e1']}}",
            ):
                self.assertIn(instruction, agent.instruction)

    def test_agent_instruction_carries_the_migration_domain(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            agent = create_agent().build_root_agent(
                repository_tools=RepositoryTools(repo, budget=SafetyBudget()),
                ledger=ValidationLedger(),
                tracker=DuplicateTracker(),
                budget=SafetyBudget(),
                model_override=ScriptedAdkLlm(),
            )

            # Without these the Agent explores without knowing what a migration
            # analyst is looking for, which is what Run 29 measured.
            for stage in ("의존성 설치", "애플리케이션 빌드", "image 빌드", "프로덕션 기동"):
                self.assertIn(stage, agent.instruction)
            for bucket in (
                "배포 대상 후보",
                "저장소에 정의된 런타임 의존성",
                "외부 런타임 의존성",
                "배포 대상 후보에서 제외한 항목",
            ):
                self.assertIn(bucket, agent.instruction)
            self.assertIn("Dockerfile이 없는 것은 분석 실패가 아니라", agent.instruction)
            self.assertIn("conflicting으로 기록", agent.instruction)
            self.assertIn("components", agent.instruction)
            self.assertIn("결과가 0건이면", agent.instruction)
            # The old blanket ban removed the domain along with the hardcoding.
            self.assertNotIn("고정 파일 순서", agent.instruction)

    def test_instruction_focuses_on_migration_questions_not_generic_repository_summary(self):
        instruction = build_migration_instruction(DEFAULT_MIGRATION_POLICY)

        self.assertIn("production_startup", instruction)
        self.assertIn("Kubernetes", instruction)
        self.assertIn("read-only", instruction)
        self.assertIn("evidence", instruction.lower())
        self.assertIn("unresolved", instruction)
        for header in ("## Role", "## Mission", "## Policy", "## Stop"):
            self.assertIn(header, instruction)
        # The Mission explicitly denies this goal ("...목표가 아닙니다"), which is
        # fine and expected; what must never appear is the goal stated
        # affirmatively, in either word order an earlier prototype used.
        self.assertNotIn("설명하는 것이 목표입니다", instruction)
        self.assertNotIn("Repository 전체를 설명한다", instruction)
        self.assertNotIn("전체 Repository를 설명한다", instruction)

    def test_instruction_explains_how_to_read_exploration_signals(self):
        instruction = build_migration_instruction(DEFAULT_MIGRATION_POLICY)

        self.assertIn("exploration_signals", instruction)
        # Guidance only -- must not force a specific next Tool call.
        self.assertNotIn("next_tool", instruction)

    def test_instruction_lists_every_policy_question_id(self):
        instruction = build_migration_instruction(DEFAULT_MIGRATION_POLICY)

        for question in DEFAULT_MIGRATION_POLICY.questions:
            self.assertIn(question.question_id, instruction)

    def test_build_root_agent_uses_build_migration_instruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            agent = create_agent().build_root_agent(
                repository_tools=RepositoryTools(repo, budget=SafetyBudget()),
                ledger=ValidationLedger(),
                tracker=DuplicateTracker(),
                budget=SafetyBudget(),
                model_override=ScriptedAdkLlm(),
            )

            self.assertEqual(agent.instruction, build_migration_instruction(DEFAULT_MIGRATION_POLICY))

    def test_build_root_agent_shares_one_control_ledger_with_the_live_model(self):
        """Live smoke showed the model ignore a narrowed allowed-action
        instruction that only ever reached it as text. The live
        OpenAICompatibleAdkLlm path must see the same RunControlLedger
        instance the toolset callbacks enforce against, not a second one
        AdkRepositoryToolset created for itself."""

        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            control = RunControlLedger()
            agent = AgentApplication(settings=Settings()).build_root_agent(
                repository_tools=RepositoryTools(repo, budget=SafetyBudget()),
                ledger=ValidationLedger(),
                tracker=DuplicateTracker(),
                budget=SafetyBudget(),
                control=control,
            )

            self.assertIs(agent.model._control, control)

    def test_production_analyze_uses_adk_and_validates_agent_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root)
            model = ScriptedAdkLlm()
            result = analyze(repo, root / "outputs" / "analysis", adk_model=model, max_iterations=5)

            self.assertIsInstance(result, AnalysisResult)
            self.assertEqual(result.status, "complete")
            self.assertIn("Agent가", result.summary)
            self.assertEqual({item.status for item in result.evidence}, {"confirmed", "inferred", "unresolved", "conflicting"})
            self.assertEqual(model._tool_names, ["inspect_target", "search_text", "validate_analysis"])
            self.assertTrue((root / "outputs" / "analysis" / "analysis-result.json").is_file())


if __name__ == "__main__":
    unittest.main()
