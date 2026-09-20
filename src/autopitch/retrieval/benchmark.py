"""Benchmark a deck's raise against comparable rounds retrieved from the index."""

from __future__ import annotations

import statistics

from pydantic import BaseModel, Field

from autopitch.retrieval.embed import Embedder
from autopitch.retrieval.models import Match, deck_query_text
from autopitch.retrieval.store import VectorStore
from autopitch.schema import Deck

_MIN_SECTOR_HITS = 3
_HIGH_RATIO = 2.0
_LOW_RATIO = 0.5


class Benchmark(BaseModel):
    comparables: list[Match] = Field(default_factory=list)
    sector_matched: bool = True
    stage_comparables: int = 0
    median_raise_usd: float | None = None
    raise_ratio: float | None = Field(
        default=None, description="Deck raise divided by the median comparable raise"
    )
    flags: list[str] = Field(default_factory=list)


def benchmark_deck(deck: Deck, embedder: Embedder, store: VectorStore, top_k: int = 8) -> Benchmark:
    vector = embedder.embed_query(deck_query_text(deck))

    sector_matched = True
    matches = store.query(vector, top_k=top_k, sector=deck.sector)
    if len(matches) < _MIN_SECTOR_HITS:
        # Too few same-sector rounds to say anything; widen the search and say so.
        matches = store.query(vector, top_k=top_k)
        sector_matched = False

    result = Benchmark(comparables=matches, sector_matched=sector_matched)
    if not matches:
        result.flags.append("No comparable funding rounds were found in the index.")
        return result
    if not sector_matched:
        result.flags.append(
            f"Fewer than {_MIN_SECTOR_HITS} '{deck.sector}' comparables indexed; "
            "comparables below span other sectors."
        )

    same_stage = [
        m.pattern.round_amount_usd
        for m in matches
        if m.pattern.stage == deck.stage and m.pattern.round_amount_usd
    ]
    result.stage_comparables = len(same_stage)
    if not same_stage:
        result.flags.append(f"No comparables at stage '{deck.stage}' carry a disclosed amount.")
        return result

    result.median_raise_usd = statistics.median(same_stage)
    ask = deck.financials.raise_amount_usd
    if not ask:
        result.flags.append("Deck does not state a raise amount, so it cannot be benchmarked.")
        return result

    result.raise_ratio = round(ask / result.median_raise_usd, 2)
    if result.raise_ratio >= _HIGH_RATIO:
        result.flags.append(
            f"Ask of ${ask:,.0f} is {result.raise_ratio}x the median comparable "
            f"(${result.median_raise_usd:,.0f})."
        )
    elif result.raise_ratio <= _LOW_RATIO:
        result.flags.append(
            f"Ask of ${ask:,.0f} is only {result.raise_ratio}x the median comparable "
            f"(${result.median_raise_usd:,.0f}); check runway."
        )
    return result
