"""Text embedders."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

from google import genai
from google.genai import types


class Embedder(Protocol):
    dim: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class GeminiEmbedder:
    def __init__(self, api_key: str, model: str = "gemini-embedding-001", dim: int = 768) -> None:
        self.dim = dim
        self._model = model
        self._client = genai.Client(api_key=api_key)

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        resp = self._client.models.embed_content(
            model=self._model,
            contents=texts,
            config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=self.dim),
        )
        return [_normalise(list(e.values)) for e in resp.embeddings]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 100):  # API batch limit
            out.extend(self._embed(texts[i : i + 100], "RETRIEVAL_DOCUMENT"))
        return out

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "RETRIEVAL_QUERY")[0]


class HashEmbedder:
    """Feature-hashed bag of words. No network or model, so tests and demos stay offline.

    Similarity reflects word overlap only. It is not a substitute for a real model.
    """

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0
        return _normalise(v)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


def _normalise(v: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]
