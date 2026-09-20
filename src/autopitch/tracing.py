"""Opt-in LangSmith tracing.

Tracing is off unless AUTOPITCH_LANGSMITH_API_KEY is set. When on, LangGraph emits one span
per node and `TracedLLM` adds one span per model call, so a report's score can be followed
back to the exact prompt and response that produced it. Prompts contain deck text, so only
enable this for decks you are permitted to send to LangSmith.
"""

from __future__ import annotations

import os

from langsmith import traceable

from autopitch.config import Settings
from autopitch.llm.base import LLMClient, T


def configure_tracing(settings: Settings) -> bool:
    if not settings.langsmith_api_key:
        os.environ["LANGSMITH_TRACING"] = "false"
        return False
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    return True


class TracedLLM:
    """Records each call as an LLM-type span named after the wrapped model."""

    def __init__(self, inner: LLMClient) -> None:
        self.name = inner.name
        self._inner = inner

    def generate(self, system: str, prompt: str) -> str:
        @traceable(run_type="llm", name=f"{self.name}.generate")
        def call(system: str, prompt: str) -> str:
            return self._inner.generate(system, prompt)

        return call(system, prompt)

    def generate_structured(self, system: str, prompt: str, schema: type[T]) -> T:
        @traceable(run_type="llm", name=f"{self.name}.{schema.__name__}")
        def call(system: str, prompt: str) -> T:
            return self._inner.generate_structured(system, prompt, schema)

        return call(system, prompt)
