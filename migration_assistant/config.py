"""Configuration boundary for the single OpenAI-compatible model adapter."""

from __future__ import annotations

import os
from math import isfinite
from dataclasses import dataclass
from typing import Mapping


DEFAULT_LLM_BASE_URL = "https://api.upstage.ai/v1"
DEFAULT_LLM_MODEL = "solar-pro3"
DEFAULT_LLM_TIMEOUT_SECONDS = 60.0
DEFAULT_LLM_MAX_TOKENS = 4096


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings shared by the ADK application and service layers."""

    llm_base_url: str = DEFAULT_LLM_BASE_URL
    llm_api_key: str | None = None
    llm_model: str = DEFAULT_LLM_MODEL
    llm_timeout_seconds: float = DEFAULT_LLM_TIMEOUT_SECONDS
    llm_max_tokens: int = DEFAULT_LLM_MAX_TOKENS

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if environment is None else environment
        defaults = cls()
        try:
            timeout = float(values.get("LLM_TIMEOUT_SECONDS", str(DEFAULT_LLM_TIMEOUT_SECONDS)))
            max_tokens = int(values.get("LLM_MAX_TOKENS", str(DEFAULT_LLM_MAX_TOKENS)))
        except ValueError as error:
            raise ValueError("LLM_TIMEOUT_SECONDS와 LLM_MAX_TOKENS는 숫자여야 합니다.") from error

        if not isfinite(timeout) or timeout <= 0:
            raise ValueError("LLM_TIMEOUT_SECONDS는 유한한 0보다 큰 수여야 합니다.")
        if max_tokens <= 0:
            raise ValueError("LLM_MAX_TOKENS는 0보다 커야 합니다.")

        return cls(
            llm_base_url=values.get("LLM_BASE_URL", defaults.llm_base_url),
            llm_api_key=values.get("LLM_API_KEY") or None,
            llm_model=values.get("LLM_MODEL", defaults.llm_model),
            llm_timeout_seconds=timeout,
            llm_max_tokens=max_tokens,
        )

    def __repr__(self) -> str:
        api_key = "'<redacted>'" if self.llm_api_key else "None"
        return (
            "Settings("
            f"llm_base_url={self.llm_base_url!r}, "
            f"llm_api_key={api_key}, "
            f"llm_model={self.llm_model!r}, "
            f"llm_timeout_seconds={self.llm_timeout_seconds!r}, "
            f"llm_max_tokens={self.llm_max_tokens!r})"
        )
