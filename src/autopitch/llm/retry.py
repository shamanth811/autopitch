"""Retry wrapper for transient model failures."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable

from autopitch.llm.base import LLMClient, LLMError, T

log = logging.getLogger(__name__)


class RetryingLLM:
    """Retries `LLMError` with exponential backoff and jitter, then re-raises the last one."""

    def __init__(
        self,
        inner: LLMClient,
        attempts: int = 3,
        base_delay: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.name = inner.name
        self._inner = inner
        self._attempts = attempts
        self._base = base_delay
        self._sleep = sleep

    def _run(self, fn: Callable[[], T]) -> T:
        for attempt in range(1, self._attempts + 1):
            try:
                return fn()
            except LLMError as exc:
                if attempt == self._attempts:
                    raise
                delay = self._base * 2 ** (attempt - 1) * (0.5 + random.random())
                log.warning("%s attempt %d/%d failed: %s", self.name, attempt, self._attempts, exc)
                self._sleep(delay)
        raise AssertionError("unreachable")

    def generate(self, system: str, prompt: str) -> str:
        return self._run(lambda: self._inner.generate(system, prompt))

    def generate_structured(self, system: str, prompt: str, schema: type[T]) -> T:
        return self._run(lambda: self._inner.generate_structured(system, prompt, schema))
