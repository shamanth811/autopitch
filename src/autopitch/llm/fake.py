"""Deterministic in-memory client for tests and offline demos."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from autopitch.llm.base import LLMError, T

Responder = Callable[[str, str], Any]


class FakeLLM:
    """Returns canned objects keyed by schema class.

    A value may be a model instance or a callable `(system, prompt) -> instance`,
    which lets tests vary the answer by section.
    """

    def __init__(self, structured: dict[type, Any] | None = None, text: str = "ok") -> None:
        self.name = "fake"
        self.structured = structured or {}
        self.text = text
        self.calls: list[tuple[str, str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append(("text", system, prompt))
        return self.text

    def generate_structured(self, system: str, prompt: str, schema: type[T]) -> T:
        self.calls.append((schema.__name__, system, prompt))
        if schema not in self.structured:
            raise LLMError(f"FakeLLM has no response registered for {schema.__name__}")
        value = self.structured[schema]
        return value(system, prompt) if callable(value) else value
