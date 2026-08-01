"""Deterministic Python guardrail boundary; repository policy starts in T2."""

from __future__ import annotations

from typing import Protocol, TypeVar


Value = TypeVar("Value")


class Guardrail(Protocol[Value]):
    """Validates deterministic input/output constraints outside the Agent."""

    def validate(self, value: Value) -> Value:
        """Return a validated value or raise a deterministic validation error."""
