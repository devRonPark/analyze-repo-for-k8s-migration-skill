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
from migration_assistant.agent import PUBLIC_AGENT_TOOL_NAMES, create_agent
from migration_assistant.adk_tools import DuplicateTracker, ValidationLedger
from migration_assistant.repository_tools import RepositoryTools
from migration_assistant.target import SafetyBudget


class ScriptedAdkLlm(BaseLlm):
    """A deterministic ADK model used only to exercise the real Runner path."""

    model: str = "fake-test-model"
    _calls: int = PrivateAttr(0)
    _tool_names: list[str] = PrivateAttr(default_factory=list)

    async def generate_content_async(self, llm_request, stream: bool = False):
        self._calls += 1
        if self._calls == 1:
            name = "search_text"
            args = {"pattern": "PORT"}
        elif self._calls == 2:
            name = "validate_analysis"
            args = {
                "status": "complete",
                "summary": "Agent가 Repository 근거를 종합했습니다.",
                "evidence": [
                    {"status": "confirmed", "path": "app.py", "line_start": 1, "line_end": 1, "text": "PORT = 8080"},
                    {"status": "inferred", "path": "app.py", "line_start": 1, "line_end": 1, "text": "PORT = 8080"},
                    {"status": "conflicting", "path": "app.py", "line_start": 1, "line_end": 1, "text": "PORT = 8080"},
                    {"status": "unresolved", "absence_scope": "**/*.yaml", "absence_pattern": "ingress", "result": "not searched"},
                ],
                "iterations": 2,
                "errors": [],
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
            self.assertEqual(model._tool_names, ["search_text", "validate_analysis"])
            self.assertTrue((root / "outputs" / "analysis" / "analysis-result.json").is_file())


if __name__ == "__main__":
    unittest.main()
