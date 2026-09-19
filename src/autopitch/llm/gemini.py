"""Gemini client using the google-genai SDK with native JSON-schema output."""

from __future__ import annotations

from google import genai
from google.genai import types
from pydantic import ValidationError

from autopitch.llm.base import LLMError, T


class GeminiClient:
    def __init__(self, api_key: str, model: str = "gemini-2.5-pro") -> None:
        self.name = model
        self._model = model
        self._client = genai.Client(api_key=api_key)

    def generate(self, system: str, prompt: str) -> str:
        try:
            resp = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system, temperature=0.2),
            )
        except Exception as exc:  # SDK raises several unrelated exception types
            raise LLMError(f"Gemini call failed: {exc}") from exc
        return resp.text or ""

    def generate_structured(self, system: str, prompt: str, schema: type[T]) -> T:
        try:
            resp = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=0.1,
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
            return schema.model_validate_json(resp.text or "")
        except ValidationError as exc:
            raise LLMError(f"Gemini output failed validation for {schema.__name__}: {exc}") from exc
        except Exception as exc:
            raise LLMError(f"Gemini call failed: {exc}") from exc
