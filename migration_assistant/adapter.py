"""One provider-agnostic adapter for OpenAI-compatible chat completions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from .config import Settings


class AdapterConfigurationError(ValueError):
    """Raised when settings cannot describe an OpenAI-compatible endpoint."""


class AdapterRequestError(ValueError):
    """Raised when a chat completion request is not structurally valid."""


@dataclass(frozen=True, slots=True)
class ChatCompletionRequest:
    """Transport-neutral request data for an OpenAI-compatible endpoint."""

    url: str
    headers: Mapping[str, str]
    payload: Mapping[str, object]
    timeout_seconds: float

    def __repr__(self) -> str:
        header_names = tuple(self.headers)
        return (
            "ChatCompletionRequest("
            f"url={self.url!r}, "
            f"headers={header_names!r}, "
            f"payload={self.payload!r}, "
            f"timeout_seconds={self.timeout_seconds!r})"
        )


class ModelAdapter(Protocol):
    """Contract consumed by the future ADK integration."""

    def build_request(
        self, messages: Sequence[Mapping[str, object]]
    ) -> ChatCompletionRequest:
        """Build a request without performing network I/O."""


class OpenAICompatibleAdapter:
    """Build requests for any endpoint implementing the OpenAI-compatible API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._validate_settings()

    def __repr__(self) -> str:
        return (
            "OpenAICompatibleAdapter("
            f"llm_base_url={self.settings.llm_base_url!r}, "
            f"llm_model={self.settings.llm_model!r}, "
            f"llm_timeout_seconds={self.settings.llm_timeout_seconds!r}, "
            f"llm_max_tokens={self.settings.llm_max_tokens!r}, "
            "llm_api_key='<redacted>')"
        )

    def build_request(
        self, messages: Sequence[Mapping[str, object]]
    ) -> ChatCompletionRequest:
        normalized_messages = self._normalize_messages(messages)
        headers = {"Content-Type": "application/json"}
        if self.settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"

        return ChatCompletionRequest(
            url=f"{self.settings.llm_base_url.rstrip('/')}/chat/completions",
            headers=headers,
            payload={
                "model": self.settings.llm_model,
                "messages": normalized_messages,
                "max_tokens": self.settings.llm_max_tokens,
            },
            timeout_seconds=self.settings.llm_timeout_seconds,
        )

    def _validate_settings(self) -> None:
        if not isinstance(self.settings, Settings):
            raise AdapterConfigurationError("adapter에는 Settings가 필요합니다.")
        if not self.settings.llm_base_url.strip():
            raise AdapterConfigurationError("LLM_BASE_URL은 비어 있을 수 없습니다.")
        if not self.settings.llm_model.strip():
            raise AdapterConfigurationError("LLM_MODEL은 비어 있을 수 없습니다.")
        if self.settings.llm_timeout_seconds <= 0:
            raise AdapterConfigurationError("LLM_TIMEOUT_SECONDS는 0보다 커야 합니다.")
        if self.settings.llm_max_tokens <= 0:
            raise AdapterConfigurationError("LLM_MAX_TOKENS는 0보다 커야 합니다.")

    @staticmethod
    def _normalize_messages(
        messages: Sequence[Mapping[str, object]],
    ) -> list[dict[str, object]]:
        if isinstance(messages, (str, bytes)) or not messages:
            raise AdapterRequestError("messages에는 하나 이상의 message가 필요합니다.")

        normalized: list[dict[str, object]] = []
        for message in messages:
            if not isinstance(message, Mapping):
                raise AdapterRequestError("각 message는 mapping이어야 합니다.")
            role = message.get("role")
            content = message.get("content")
            if not isinstance(role, str) or not role.strip():
                raise AdapterRequestError("각 message에는 비어 있지 않은 role이 필요합니다.")
            if not isinstance(content, str):
                raise AdapterRequestError("각 message에는 문자열 content가 필요합니다.")
            normalized.append(dict(message))
        return normalized
