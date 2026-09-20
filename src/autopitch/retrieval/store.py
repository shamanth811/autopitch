"""Vector stores for funding patterns: Pinecone in production, in-memory for tests."""

from __future__ import annotations

import math
from typing import Protocol

from pinecone import Pinecone, ServerlessSpec

from autopitch.retrieval.models import FundingPattern, Match


class VectorStore(Protocol):
    def upsert(self, patterns: list[FundingPattern], vectors: list[list[float]]) -> None: ...

    def query(self, vector: list[float], top_k: int, sector: str | None = None) -> list[Match]: ...


def _to_metadata(p: FundingPattern) -> dict:
    # Pinecone metadata cannot hold nulls, so absent values are dropped.
    meta = p.model_dump(exclude_none=True)
    meta["investors"] = list(p.investors)
    return meta


class PineconeStore:
    def __init__(self, api_key: str, index_name: str, namespace: str, dim: int) -> None:
        self._pc = Pinecone(api_key=api_key)
        self._namespace = namespace
        if not self._pc.has_index(index_name):
            self._pc.create_index(
                name=index_name,
                dimension=dim,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
        self._index = self._pc.Index(index_name)

    def upsert(self, patterns: list[FundingPattern], vectors: list[list[float]]) -> None:
        records = [
            {"id": p.id, "values": v, "metadata": _to_metadata(p)}
            for p, v in zip(patterns, vectors, strict=True)
        ]
        for i in range(0, len(records), 100):
            self._index.upsert(vectors=records[i : i + 100], namespace=self._namespace)

    def query(self, vector: list[float], top_k: int, sector: str | None = None) -> list[Match]:
        resp = self._index.query(
            vector=vector,
            top_k=top_k,
            namespace=self._namespace,
            filter={"sector": {"$eq": sector}} if sector else None,
            include_metadata=True,
        )
        return [
            Match(pattern=FundingPattern(**m.metadata), similarity=float(m.score))
            for m in resp.matches
        ]


class InMemoryStore:
    def __init__(self) -> None:
        self._rows: list[tuple[FundingPattern, list[float]]] = []

    def upsert(self, patterns: list[FundingPattern], vectors: list[list[float]]) -> None:
        existing = {p.id: i for i, (p, _) in enumerate(self._rows)}
        for p, v in zip(patterns, vectors, strict=True):
            if p.id in existing:
                self._rows[existing[p.id]] = (p, v)
            else:
                self._rows.append((p, v))

    def query(self, vector: list[float], top_k: int, sector: str | None = None) -> list[Match]:
        rows = [(p, v) for p, v in self._rows if sector is None or p.sector == sector]
        scored = [Match(pattern=p, similarity=_cosine(vector, v)) for p, v in rows]
        return sorted(scored, key=lambda m: m.similarity, reverse=True)[:top_k]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
