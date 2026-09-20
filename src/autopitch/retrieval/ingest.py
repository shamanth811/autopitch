"""Filing -> funding patterns -> embeddings -> vector store."""

from __future__ import annotations

import logging
import re

import httpx
from pydantic import BaseModel, Field

from autopitch.llm import LLMClient, LLMError
from autopitch.retrieval.edgar import EdgarClient, FilingRef
from autopitch.retrieval.embed import Embedder
from autopitch.retrieval.models import FundingPattern, pattern_text
from autopitch.retrieval.store import VectorStore

log = logging.getLogger(__name__)

_SECTION_MARKERS = (
    "recent sales of unregistered securities",
    "convertible preferred stock financing",
    "preferred stock financings",
)
_EXCERPT_CHARS = 30_000

_SYSTEM = """You extract private financing rounds from the text of an SEC registration statement.
Rules:
- Return only rounds in which the company sold preferred stock, convertible notes or SAFEs to
  investors before the IPO. Ignore option grants, warrants and share issuances to employees.
- `round_amount_usd` is the aggregate proceeds in USD when stated, otherwise null.
- `stage` is one of: pre-seed, seed, series-a, series-b, later. Map Series C and beyond to later.
- `sector` is a short lowercase label for what the company does (e.g. fintech, climate, devtools).
- `summary` is one factual sentence about the round and the business. Do not add opinions.
- Never invent investors, amounts or dates that are not in the text.
"""


class _ExtractedRound(BaseModel):
    stage: str | None = None
    round_amount_usd: float | None = None
    year: int | None = None
    investors: list[str] = Field(default_factory=list)
    summary: str


class _ExtractedRounds(BaseModel):
    sector: str = "unknown"
    rounds: list[_ExtractedRound] = Field(default_factory=list)


def find_financing_excerpt(text: str) -> str | None:
    """Locate the financing disclosure. Uses the last marker hit, because earlier hits are
    usually the table of contents or a cross-reference."""
    lowered = text.lower()
    best = -1
    for marker in _SECTION_MARKERS:
        best = max(best, lowered.rfind(marker))
    if best < 0:
        return None
    return text[best : best + _EXCERPT_CHARS]


def extract_patterns(ref: FilingRef, text: str, llm: LLMClient) -> list[FundingPattern]:
    excerpt = find_financing_excerpt(text)
    if excerpt is None:
        return []
    prompt = f"Company: {ref.company}\nFiling: {ref.form} filed {ref.filed}\n\n{excerpt}"
    extracted = llm.generate_structured(_SYSTEM, prompt, _ExtractedRounds)
    slug = re.sub(r"[^a-z0-9]+", "-", ref.company.lower()).strip("-")
    return [
        FundingPattern(
            id=f"{ref.accession}-{slug}-{i}",
            company=ref.company,
            sector=extracted.sector.lower(),
            stage=r.stage,
            round_amount_usd=r.round_amount_usd,
            year=r.year,
            investors=r.investors,
            summary=r.summary,
            source_url=ref.url,
        )
        for i, r in enumerate(extracted.rounds)
    ]


def ingest_filings(
    refs: list[FilingRef],
    edgar: EdgarClient,
    llm: LLMClient,
    embedder: Embedder,
    store: VectorStore,
) -> int:
    """Ingest each filing independently so one bad filing does not abort the run.
    Returns the number of patterns stored."""
    stored = 0
    for ref in refs:
        try:
            patterns = extract_patterns(ref, edgar.fetch_text(ref), llm)
        except (LLMError, httpx.HTTPError) as exc:
            log.warning("skipping %s (%s): %s", ref.company, ref.accession, exc)
            continue
        if not patterns:
            log.info("no financing section found in %s (%s)", ref.company, ref.accession)
            continue
        store.upsert(patterns, embedder.embed_documents([pattern_text(p) for p in patterns]))
        stored += len(patterns)
        log.info("stored %d patterns from %s", len(patterns), ref.company)
    return stored
