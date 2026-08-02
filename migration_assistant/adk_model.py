"""Provider-neutral Google ADK BaseLlm bridge for the OpenAI-compatible adapter."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Mapping

from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types
from pydantic import PrivateAttr

from .adapter import OpenAICompatibleAdapter
from .config import Settings
from .repository_tools import redact_sensitive_value
from .target import SafetyBudget
from .tool_contract import PUBLIC_AGENT_TOOL_NAMES


class OpenAICompatibleAdkLlm(BaseLlm):
    """Translate ADK requests/responses without provider-specific branches."""

    _adapter: OpenAICompatibleAdapter = PrivateAttr()
    _budget: SafetyBudget = PrivateAttr()

    def __init__(self, settings: Settings, *, budget: SafetyBudget) -> None:
        super().__init__(model=settings.llm_model)
        self._adapter = OpenAICompatibleAdapter(settings)
        self._budget = budget

    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False):
        self._budget.consume_iteration()
        messages = self._messages(llm_request)
        tools = self._tools(llm_request)
        response = await asyncio.to_thread(self._adapter.complete, messages, tools=tools or None)
        yield self._response(response)

    @classmethod
    def _messages(cls, request: LlmRequest) -> list[dict[str, object]]:
        messages: list[dict[str, object]] = []
        system = request.config.system_instruction
        system_text = cls._text(system)
        if system_text:
            messages.append({"role": "system", "content": system_text})
        for content in request.contents:
            role = "assistant" if content.role == "model" else (content.role or "user")
            text_parts: list[str] = []
            tool_calls: list[dict[str, object]] = []
            tool_messages: list[dict[str, object]] = []
            for part in content.parts or []:
                if part.text:
                    text_parts.append(str(redact_sensitive_value(part.text)))
                if part.function_call:
                    call = part.function_call
                    tool_calls.append(
                        {
                            "id": call.id or f"adk-{call.name}",
                            "type": "function",
                            "function": {"name": call.name, "arguments": json.dumps(redact_sensitive_value(call.args or {}), ensure_ascii=False)},
                        }
                    )
                if part.function_response:
                    response = part.function_response
                    tool_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": response.id or f"adk-{response.name}",
                            "content": json.dumps(redact_sensitive_value(response.response or {}), ensure_ascii=False),
                        }
                    )
            if tool_messages:
                messages.extend(tool_messages)
                if not text_parts and not tool_calls:
                    continue
            message: dict[str, object] = {"role": role, "content": "\n".join(text_parts) if text_parts else None}
            if tool_calls:
                message["tool_calls"] = tool_calls
            if message["content"] is None and not tool_calls:
                message["content"] = ""
            messages.append(message)
        return cls._bound_messages(cls._ensure_tool_results(messages))

    @staticmethod
    def _bound_messages(messages: list[dict[str, object]], max_bytes: int = 160 * 1024) -> list[dict[str, object]]:
        """Keep recent complete tool-call turns within the adapter context budget."""
        if not messages:
            return messages
        system = [messages[0]] if messages[0].get("role") == "system" else []
        body = messages[len(system):]
        chunks: list[list[dict[str, object]]] = []
        current: list[dict[str, object]] = []
        for message in body:
            role = message.get("role")
            if role == "assistant" and message.get("tool_calls"):
                if current:
                    chunks.append(current)
                current = [message]
            elif role == "tool":
                current.append(message)
            else:
                if current:
                    chunks.append(current)
                current = [message]
        if current:
            chunks.append(current)

        selected: list[list[dict[str, object]]] = []
        size = len(json.dumps(system, ensure_ascii=False).encode("utf-8"))
        for chunk in reversed(chunks):
            chunk_size = len(json.dumps(chunk, ensure_ascii=False).encode("utf-8"))
            if selected and size + chunk_size > max_bytes:
                break
            if not selected and size + chunk_size > max_bytes:
                selected.append(chunk)
                break
            selected.append(chunk)
            size += chunk_size
        selected.reverse()
        compacted = [item for chunk in selected for item in chunk]
        if chunks and len(selected) < len(chunks):
            note = {
                "role": "user",
                "content": "이전 대화의 오래된 tool 결과는 context budget 때문에 생략되었습니다. 생략된 관찰을 추정하지 말고 필요한 사실은 Repository Tool로 다시 확인하세요.",
            }
            compacted.insert(0, note)
        return system + compacted

    @staticmethod
    def _ensure_tool_results(messages: list[dict[str, object]]) -> list[dict[str, object]]:
        """Heal interrupted ADK histories before an OpenAI-compatible request."""
        healed: list[dict[str, object]] = []
        pending: list[str] = []
        for message in messages:
            role = message.get("role")
            if pending and role != "tool":
                healed.extend(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(
                            {
                                "valid": False,
                                "error": "Tool response가 누락되어 실행되지 않았습니다.",
                            },
                            ensure_ascii=False,
                        ),
                    }
                    for call_id in pending
                )
                pending = []
            if role == "assistant":
                pending = [
                    str(call.get("id"))
                    for call in message.get("tool_calls", [])
                    if isinstance(call, Mapping) and call.get("id")
                ]
            elif role == "tool":
                call_id = message.get("tool_call_id")
                if call_id in pending:
                    pending.remove(call_id)
            healed.append(message)
        if pending:
            healed.extend(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(
                        {"valid": False, "error": "Tool response가 누락되어 실행되지 않았습니다."},
                        ensure_ascii=False,
                    ),
                }
                for call_id in pending
            )
        return healed

    @classmethod
    def _tools(cls, request: LlmRequest) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for tool in request.config.tools or []:
            for declaration in tool.function_declarations or []:
                parameters = getattr(declaration, "parameters_json_schema", None)
                if parameters is None:
                    parameters = declaration.parameters
                if hasattr(parameters, "model_dump"):
                    parameters = parameters.model_dump(exclude_none=True, by_alias=True)
                parameters = cls._json_schema(parameters)
                result.append(
                    {
                        "type": "function",
                        "function": {
                            "name": declaration.name,
                            "description": declaration.description or "",
                            "parameters": parameters or {"type": "object", "properties": {}},
                        },
                    }
                )
        return result

    @classmethod
    def _json_schema(cls, value: object) -> object:
        """Translate google.genai's OpenAPI-flavoured schema to JSON Schema.

        ADK uses the Gemini schema model even when the model boundary is a
        provider-neutral OpenAI-compatible endpoint.  The translation belongs
        here, at that boundary; repository and agent logic must not know about
        either schema dialect.
        """
        if isinstance(value, Mapping):
            normalized: dict[str, object] = {}
            aliases = {
                "anyOf": "anyOf",
                "maxItems": "maxItems",
                "maxLength": "maxLength",
                "maxProperties": "maxProperties",
                "minItems": "minItems",
                "minLength": "minLength",
                "minProperties": "minProperties",
                "additionalProperties": "additionalProperties",
            }
            allowed = {
                "type", "properties", "items", "required", "description",
                "enum", "format", "pattern", "minimum", "maximum",
                "minItems", "maxItems", "minLength", "maxLength",
                "minProperties", "maxProperties", "additionalProperties",
                "anyOf", "allOf", "oneOf", "$ref", "$defs", "default",
            }
            for raw_key, raw_value in value.items():
                key = aliases.get(str(raw_key), str(raw_key))
                if key in {"nullable", "propertyOrdering", "example", "title", "ref", "defs"}:
                    continue
                if key not in allowed:
                    continue
                if key == "type" and raw_value is not None:
                    type_value = getattr(raw_value, "value", raw_value)
                    normalized[key] = str(type_value).lower()
                elif key == "properties" and isinstance(raw_value, Mapping):
                    normalized[key] = {
                        str(name): cls._json_schema(schema)
                        for name, schema in raw_value.items()
                    }
                elif key == "required" and isinstance(raw_value, list):
                    normalized[key] = [str(item) for item in raw_value]
                elif key in {"items", "additionalProperties"}:
                    normalized[key] = cls._json_schema(raw_value)
                elif key in {"anyOf", "allOf", "oneOf"} and isinstance(raw_value, list):
                    normalized[key] = [cls._json_schema(item) for item in raw_value]
                else:
                    normalized[key] = raw_value
            if "type" not in normalized and "properties" in normalized:
                normalized["type"] = "object"
            return normalized
        if isinstance(value, list):
            return [cls._json_schema(item) for item in value]
        return value

    @staticmethod
    def _text(value: Any) -> str:
        if isinstance(value, str):
            return value
        if value is None:
            return ""
        return "\n".join(part.text for part in (value.parts or []) if getattr(part, "text", None))

    @classmethod
    def _response(cls, response: Mapping[str, object]) -> LlmResponse:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            raise ValueError("LLM response에 choices가 없습니다.")
        message = choices[0].get("message")
        if not isinstance(message, Mapping):
            raise ValueError("LLM response에 message가 없습니다.")
        parts: list[types.Part] = []
        content = message.get("content")
        if isinstance(content, str) and content:
            parts.append(types.Part(text=content))
        calls = message.get("tool_calls")
        if isinstance(calls, list):
            for call in calls:
                if not isinstance(call, Mapping):
                    continue
                function = call.get("function")
                if not isinstance(function, Mapping) or not isinstance(function.get("name"), str):
                    continue
                arguments = function.get("arguments", "{}")
                name, embedded_arguments = cls._normalize_function_call(str(function["name"]), arguments)
                if embedded_arguments is not None and (not isinstance(arguments, str) or arguments in {"", "{}"}):
                    arguments = embedded_arguments
                if isinstance(arguments, str):
                    try:
                        args = json.loads(arguments)
                    except json.JSONDecodeError:
                        args = {}
                else:
                    args = arguments if isinstance(arguments, dict) else {}
                parts.append(types.Part(functionCall=types.FunctionCall(name=name, args=args, id=call.get("id"))))
        return LlmResponse(content=types.Content(role="model", parts=parts), partial=False)

    @staticmethod
    def _normalize_function_call(name: str, arguments: object) -> tuple[str, dict[str, object] | None]:
        """Recover a public tool name from a malformed provider-neutral function field."""
        if name in PUBLIC_AGENT_TOOL_NAMES:
            return name, None
        for public_name in sorted(PUBLIC_AGENT_TOOL_NAMES, key=len, reverse=True):
            compact_name = name.replace("_", "")
            compact_public_name = public_name.replace("_", "")
            if compact_name == compact_public_name:
                return public_name, None
            if name.startswith(public_name):
                suffix = name[len(public_name):].lstrip()
            else:
                brace = name.find("{")
                raw_prefix = name if brace < 0 else name[:brace]
                if raw_prefix.replace("_", "") != compact_public_name and not raw_prefix.replace("_", "").startswith(compact_public_name):
                    continue
                suffix = name[len(raw_prefix):].lstrip()
                prefix_tail = raw_prefix.replace("_", "")[len(compact_public_name):]
                suffix = prefix_tail + suffix
            if not suffix:
                continue
            if suffix in {":", "arg", "args", "argument", "arguments"}:
                return public_name, None
            if suffix.startswith("args"):
                suffix = suffix[4:].lstrip()
            if suffix.startswith(":"):
                suffix = suffix[1:].lstrip()
            if suffix.startswith("{") and suffix.endswith("}"):
                try:
                    decoded = json.loads(suffix)
                except json.JSONDecodeError:
                    return name, None
                if isinstance(decoded, dict):
                    return public_name, decoded
        return name, None
