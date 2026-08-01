"""Live OpenAI-compatible planner for bounded repository exploration."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Protocol

from .agent import PUBLIC_AGENT_TOOL_NAMES


class CompletionAdapter(Protocol):
    def complete(
        self,
        messages: list[dict[str, object]],
        *,
        tools: list[dict[str, object]],
        response_format: Mapping[str, object] | None = None,
    ) -> Mapping[str, object]: ...


def _tool(name: str, description: str, properties: Mapping[str, object], required: list[str] | None = None) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": dict(properties),
                "required": required or [],
                "additionalProperties": False,
            },
        },
    }


REPOSITORY_TOOLS: list[dict[str, object]] = [
    _tool("inspect_target", "대상 Repository의 안전 경계와 Git 여부를 확인합니다.", {}),
    _tool("list_tree", "Repository-relative tree를 관찰합니다.", {"relative": {"type": "string"}, "max_depth": {"type": ["integer", "null"]}}),
    _tool("find_files", "Repository-relative glob으로 파일 후보를 찾습니다.", {"pattern": {"type": "string"}}, ["pattern"]),
    _tool("search_text", "파일 내용에서 정규식 패턴과 line 근거를 찾습니다.", {"pattern": {"type": "string"}, "relative": {"type": "string"}}, ["pattern"]),
    _tool("read_file", "Repository-relative file을 안전하게 읽습니다.", {"relative": {"type": "string"}}, ["relative"]),
    _tool("read_file_lines", "Repository-relative file의 지정 line 범위를 읽습니다.", {"relative": {"type": "string"}, "line_start": {"type": "integer"}, "line_end": {"type": "integer"}}, ["relative", "line_start", "line_end"]),
    _tool("inspect_git_metadata", "Git branch, HEAD, status를 관찰합니다.", {}),
    _tool("validate_analysis", "수집한 evidence의 repository path와 line 근거를 검증합니다.", {"analysis": {"type": "object"}}, ["analysis"]),
]


class LiveRepositoryPlanner:
    """Translate model tool calls into the bounded Planner protocol."""

    def __init__(self, adapter: CompletionAdapter) -> None:
        self.adapter = adapter
        self.messages: list[dict[str, object]] = [
            {
                "role": "system",
                "content": (
                    "Local Git Repository를 한국어로 근거 기반 분석합니다. "
                    "관찰 가능한 사실은 반드시 Repository Tool로 수집하고, "
                    "충분한 근거를 얻으면 {\"stop\": true} JSON object로 종료합니다. "
                    "Repository 코드나 build를 실행하지 않습니다."
                ),
            },
            {
                "role": "user",
                "content": "Repository의 실행 후보, build/runtime 근거, port/env 관련 사실을 탐색하세요.",
            },
        ]
        self._pending_tool_call: dict[str, object] | None = None

    def next_action(self, observation: object) -> Mapping[str, object]:
        if self._pending_tool_call is not None:
            pending = self._pending_tool_call
            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": pending["id"],
                    "content": json.dumps(observation, ensure_ascii=False),
                }
            )
            self._pending_tool_call = None

        response = self.adapter.complete(
            list(self.messages),
            tools=REPOSITORY_TOOLS,
            response_format=None,
        )
        message = self._message(response)

        calls = message.get("tool_calls")
        if calls:
            if not isinstance(calls, list) or len(calls) != 1 or not isinstance(calls[0], Mapping):
                raise ValueError("Agent는 한 번에 하나의 Repository Tool만 호출해야 합니다.")
            call = calls[0]
            function = call.get("function")
            if not isinstance(function, Mapping):
                raise ValueError("Agent tool call의 function 형식이 올바르지 않습니다.")
            name = function.get("name")
            if name not in PUBLIC_AGENT_TOOL_NAMES:
                raise ValueError("공개되지 않은 Repository Tool 호출입니다.")
            arguments = function.get("arguments", "{}")
            try:
                args: Any = json.loads(arguments) if isinstance(arguments, str) else arguments
            except json.JSONDecodeError as error:
                raise ValueError("Agent tool call arguments가 JSON이 아닙니다.") from error
            if not isinstance(args, Mapping):
                raise ValueError("Agent tool call arguments는 object여야 합니다.")
            call_id = call.get("id")
            if not isinstance(call_id, str) or not call_id:
                raise ValueError("Agent tool call id가 없습니다.")
            self.messages.append(message)
            self._pending_tool_call = {"id": call_id, "assistant_message": message}
            return {"tool": name, "args": dict(args)}

        self.messages.append(message)
        content = message.get("content")
        if not isinstance(content, str):
            raise ValueError("Agent 응답에 tool call 또는 JSON content가 없습니다.")
        try:
            action = json.loads(content)
        except json.JSONDecodeError as error:
            raise ValueError("Agent 종료 응답이 JSON이 아닙니다.") from error
        if not isinstance(action, Mapping) or action.get("stop") is not True:
            raise ValueError("Agent 종료 응답은 {\"stop\": true}여야 합니다.")
        return {"stop": True}

    @staticmethod
    def _message(response: Mapping[str, object]) -> dict[str, object]:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            raise ValueError("LLM response에 choices가 없습니다.")
        message = choices[0].get("message")
        if not isinstance(message, Mapping):
            raise ValueError("LLM response에 message가 없습니다.")
        return dict(message)
