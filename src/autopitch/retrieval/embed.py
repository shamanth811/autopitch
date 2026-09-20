"""Text embedders."""

from __future__ import annotations

import hashlib
import logging
import math
import random
import re
import time
from typing import Protocol

import httpx
from google import genai
from google.genai import types

log = logging.getLogger(__name__)


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


class VoyageEmbedder:
    """Voyage AI embeddings over plain HTTPS (no SDK).

    The voyage-4 family shares one embedding space, so documents and queries may use
    different sizes of model. Retries 429/5xx with backoff: accounts without a payment
    method have low request-per-minute limits.
    """

    _URL = "https://api.voyageai.com/v1/embeddings"
    _BATCH = 128

    def __init__(
        self,
        api_key: str,
        model: str = "voyage-4",
        dim: int = 1024,
        client: httpx.Client | None = None,
        attempts: int = 5,
        min_interval: float = 0.0,
        sleep=time.sleep,
        clock=time.monotonic,
    ) -> None:
        self.dim = dim
        self._min_interval = min_interval
        self._clock = clock
        self._last_call: float | None = None
        self._model = model
        self._attempts = attempts
        self._sleep = sleep
        self._http = client or httpx.Client(timeout=30.0)
        self._headers = {"Authorization": f"Bearer {api_key}"}

    def _embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        body = {
            "input": texts,
            "model": self._model,
            "input_type": input_type,
            "output_dimension": self.dim,
        }
        for attempt in range(1, self._attempts + 1):
            self._pace()
            resp = self._http.post(self._URL, json=body, headers=self._headers)
            retryable = resp.status_code == 429 or resp.status_code >= 500
            if retryable and attempt < self._attempts:
                wait = float(resp.headers.get("Retry-After") or 2**attempt)
                log.warning("voyage returned %s, retrying in %.0fs", resp.status_code, wait)
                self._sleep(wait * (1 + random.random() * 0.25))
                continue
            resp.raise_for_status()
            rows = sorted(resp.json()["data"], key=lambda r: r["index"])
            return [_normalise(r["embedding"]) for r in rows]
        raise AssertionError("unreachable")

    def _pace(self) -> None:
        """Space calls at least `min_interval` apart (free accounts allow a few per minute)."""
        if self._last_call is not None:
            wait = self._min_interval - (self._clock() - self._last_call)
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._clock()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self._BATCH):
            out.extend(self._embed(texts[i : i + self._BATCH], "document"))
        return out

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "query")[0]


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
