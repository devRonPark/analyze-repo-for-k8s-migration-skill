"""Application Service boundary between UI/entrypoints and the ADK runner."""

from __future__ import annotations

from dataclasses import dataclass

from .agent import AgentApplication, create_agent
from .config import Settings


@dataclass(frozen=True, slots=True)
class ApplicationService:
    """Owns future orchestration without owning repository or artifact details."""

    settings: Settings
    agent: AgentApplication

    @classmethod
    def from_environment(cls) -> "ApplicationService":
        settings = Settings.from_environment()
        return cls(settings=settings, agent=create_agent(settings))
