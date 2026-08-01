"""Single-Agent application boundary for the future Google ADK runner."""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import Settings


PUBLIC_AGENT_TOOL_NAMES = (
    "inspect_target",
    "list_tree",
    "find_files",
    "search_text",
    "read_file",
    "read_file_lines",
    "inspect_git_metadata",
    "validate_analysis",
)


@dataclass(frozen=True, slots=True)
class AgentApplication:
    """Configuration object that later tasks connect to one Google ADK Agent."""

    settings: Settings
    tool_names: tuple[str, ...] = field(default=PUBLIC_AGENT_TOOL_NAMES)

    @property
    def name(self) -> str:
        return "repository_migration_agent"

    def build_root_agent(self) -> object:
        """Load Google ADK only when the executable Agent is requested."""
        try:
            from google.adk.agents import Agent
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "Google ADK dependency가 설치되지 않아 Agent를 시작할 수 없습니다."
            ) from error

        return Agent(
            name=self.name,
            model=self.settings.llm_model,
            instruction="Local Git Repository를 근거 기반으로 분석하는 단일 Agent입니다.",
            tools=[],
        )


def create_agent(settings: Settings | None = None) -> AgentApplication:
    return AgentApplication(settings=settings or Settings.from_environment())
