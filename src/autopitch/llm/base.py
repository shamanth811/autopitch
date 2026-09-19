"""Provider-agnostic LLM interface.

Pipeline stages depend on `LLMClient`, never on a vendor SDK, so models can be
swapped per stage and the whole graph can run against a fake in tests.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Raised when a model call fails or returns output that does not validate."""


class LLMClient(Protocol):
    name: str

    def generate(self, system: str, prompt: str) -> str:
        """Free-text completion."""

    def generate_structured(self, system: str, prompt: str, schema: type[T]) -> T:
        """Completion constrained to, and validated against, a pydantic schema."""
