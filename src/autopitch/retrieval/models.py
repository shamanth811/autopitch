"""Records stored in the vector index and returned by retrieval."""

from __future__ import annotations

from pydantic import BaseModel, Field

from autopitch.schema import Deck


class FundingPattern(BaseModel):
    """One private financing round disclosed in an SEC filing (typically an S-1)."""

    id: str
    company: str
    sector: str
    stage: str | None = None
    round_amount_usd: float | None = None
    year: int | None = None
    investors: list[str] = Field(default_factory=list)
    summary: str = Field(description="Plain-language description used for embedding")
    source_url: str = ""


class Match(BaseModel):
    pattern: FundingPattern
    similarity: float


def pattern_text(p: FundingPattern) -> str:
    """Text that gets embedded for a stored pattern."""
    amount = f"${p.round_amount_usd:,.0f}" if p.round_amount_usd else "undisclosed amount"
    head = f"{p.sector} company, {p.stage or 'unknown'} round, {amount}, {p.year or 'n/a'}."
    return f"{head} {p.summary}"


def deck_query_text(deck: Deck) -> str:
    """Query text built from the deck, phrased like the stored pattern text."""
    raise_amt = deck.financials.raise_amount_usd
    amount = f"${raise_amt:,.0f}" if raise_amt else "undisclosed amount"
    parts = [f"{deck.sector} company, {deck.stage or 'unknown'} round, {amount}."]
    if deck.one_liner:
        parts.append(deck.one_liner)
    if deck.traction.arr_usd:
        parts.append(f"ARR ${deck.traction.arr_usd:,.0f}.")
    return " ".join(parts)
