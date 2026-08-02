"""Explicit ADK Tool declarations with local Pydantic argument validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from google.adk.tools import BaseTool
from google.genai import types
from pydantic import BaseModel, ValidationError

from .repository_tools import RepositoryToolError, redact_sensitive_text
from .target import BudgetExceededError
from .tool_protocol import ToolErrorCode, ToolIssue, error_envelope, success_envelope


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    """Raw handler result plus non-semantic execution metadata."""

    data: Any
    meta: Mapping[str, Any] = field(default_factory=dict)


class ToolRejectedError(RuntimeError):
    """A typed, expected Tool rejection that is safe to return to the model."""

    def __init__(
        self,
        issue: ToolIssue,
        *,
        allowed_next_actions: Sequence[str] = (),
        meta: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(issue.message)
        self.issue = issue
        self.allowed_next_actions = tuple(allowed_next_actions)
        self.meta = dict(meta or {})


def _field_path(error: Mapping[str, Any]) -> str:
    location = error.get("loc")
    if not isinstance(location, tuple) or not location:
        return "$"
    path = "$"
    for item in location:
        path += f"[{item}]" if isinstance(item, int) else f".{item}"
    return path


class RepositoryFunctionTool(BaseTool):
    """An explicit public Tool with one declaration and one result envelope."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        input_model: type[BaseModel],
        handler: Callable[[BaseModel], Any],
        validation_error_code: ToolErrorCode = ToolErrorCode.INVALID_ARGUMENTS,
        invalid_argument_actions: Sequence[str] = (),
    ) -> None:
        super().__init__(name=name, description=description)
        self.input_model = input_model
        self._handler = handler
        self._validation_error_code = validation_error_code
        self._invalid_argument_actions = tuple(invalid_argument_actions or (name,))

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters_json_schema=self.input_model.model_json_schema(),
        )

    def invoke(self, args: object) -> dict[str, Any]:
        """Validate and execute synchronously; ADK delegates to this same boundary."""

        try:
            validated = self.input_model.model_validate(args)
        except ValidationError as error:
            first = error.errors(include_url=False)[0]
            message = redact_sensitive_text(str(first.get("msg", "arguments are invalid")))
            return error_envelope(
                ToolIssue(
                    code=self._validation_error_code,
                    category="validation",
                    message=message,
                    field_path=_field_path(first),
                    retryable=True,
                ),
                allowed_next_actions=self._invalid_argument_actions,
            )

        try:
            result = self._handler(validated)
        except ToolRejectedError as error:
            return error_envelope(
                error.issue,
                allowed_next_actions=error.allowed_next_actions,
                meta=error.meta,
            )
        except RepositoryToolError as error:
            return error_envelope(
                ToolIssue(
                    code=error.issue.code,
                    category=error.issue.category,
                    message=redact_sensitive_text(error.issue.message),
                    field_path=error.issue.field_path,
                    retryable=error.issue.retryable,
                ),
                allowed_next_actions=error.allowed_next_actions,
            )
        except BudgetExceededError as error:
            return error_envelope(
                ToolIssue(
                    code=ToolErrorCode.BUDGET_EXHAUSTED,
                    category="resource",
                    message=redact_sensitive_text(str(error)),
                    retryable=False,
                ),
                allowed_next_actions=("validate_analysis",),
            )

        if isinstance(result, ToolExecutionResult):
            return success_envelope(result.data, meta=result.meta)
        if (
            isinstance(result, dict)
            and set(("ok", "data", "error", "meta")).issubset(result)
            and isinstance(result.get("ok"), bool)
        ):
            return result
        return success_envelope(result)

    async def run_async(self, *, args: dict[str, Any], tool_context: Any) -> dict[str, Any]:
        return self.invoke(args)
