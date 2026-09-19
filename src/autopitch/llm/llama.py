"""Llama 3.1 client for any OpenAI-compatible endpoint (Groq, Together, vLLM, Ollama)."""

from __future__ import annotations

import json

from openai import OpenAI
from pydantic import ValidationError

from autopitch.llm.base import LLMError, T

_MAX_ATTEMPTS = 2


class LlamaClient:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.name = model
        self._model = model
        self._client = OpenAI(base_url=base_url, api_key=api_key or "not-needed")

    def _chat(self, system: str, prompt: str, *, json_mode: bool = False) -> str:
        kwargs: dict = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                **kwargs,
            )
        except Exception as exc:
            raise LLMError(f"Llama call failed: {exc}") from exc
        return resp.choices[0].message.content or ""

    def generate(self, system: str, prompt: str) -> str:
        return self._chat(system, prompt)

    def generate_structured(self, system: str, prompt: str, schema: type[T]) -> T:
        # Llama 3.1 has no schema-constrained decoding on most hosts, so the schema is
        # embedded in the prompt and the reply is validated, with one corrective retry.
        schema_json = json.dumps(schema.model_json_schema())
        full_system = (
            f"{system}\n\nRespond with a single JSON object that conforms to this JSON Schema. "
            f"No prose, no markdown fences.\n{schema_json}"
        )
        last_error: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            hint = "" if attempt == 0 else f"\n\nYour previous reply was invalid: {last_error}"
            raw = self._chat(full_system, prompt + hint, json_mode=True)
            try:
                return schema.model_validate_json(raw)
            except ValidationError as exc:
                last_error = exc
        raise LLMError(f"Llama output failed validation for {schema.__name__}: {last_error}")
