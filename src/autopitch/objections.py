"""Weak-section detection and investor-objection generation."""

from __future__ import annotations

from pydantic import BaseModel, Field

from autopitch.llm import LLMClient
from autopitch.retrieval.benchmark import Benchmark
from autopitch.safety import notice, wrap_untrusted
from autopitch.schema import Deck, Section, SectionScore

WEAK_THRESHOLD = 5.0
_MAX_OBJECTIONS = 6

_SYSTEM = f"""You are a partner at a venture fund that invests in the company's sector.
{notice("analysis")}
You have just read this pitch deck and the analysis below. List the objections you would most
likely raise in the partner meeting.
- Ground every objection in the provided scores, missing data or benchmark findings.
  Do not raise objections the analysis gives no basis for.
- Be specific to the sector and stage; avoid generic startup advice.
- `question` is phrased as the investor would say it. `suggested_response` is what evidence the
  founder should bring to answer it, not a scripted answer.
- Order by how likely the objection is to end the conversation, most likely first.
"""


class Objection(BaseModel):
    section: Section
    question: str
    basis: str = Field(description="The score, gap or benchmark finding that prompts it")
    suggested_response: str


class _Objections(BaseModel):
    objections: list[Objection]


def weak_sections(scores: list[SectionScore], threshold: float = WEAK_THRESHOLD) -> list[Section]:
    """Sections scoring under the threshold, weakest first. Unscorable sections count as weak."""
    flagged = [s for s in scores if s.score < threshold or not s.criteria]
    return [s.section for s in sorted(flagged, key=lambda s: s.score)]


def _prompt(deck: Deck, scores: list[SectionScore], benchmark: Benchmark | None) -> str:
    lines = [f"Company: {deck.company} | Sector: {deck.sector} | Stage: {deck.stage or 'unknown'}"]
    lines.append("\nSection scores (0-10):")
    for s in sorted(scores, key=lambda s: s.score):
        lines.append(f"- {s.section.value}: {s.score} - {s.summary}")
        lines.extend(f"    missing: {m}" for m in s.missing_data)
    if benchmark is not None:
        lines.append("\nBenchmark findings:")
        lines.extend(f"- {f}" for f in benchmark.flags or ["No anomalies against comparables."])
        for m in benchmark.comparables[:5]:
            p = m.pattern
            amount = f"${p.round_amount_usd:,.0f}" if p.round_amount_usd else "n/a"
            lines.append(f"  comparable: {p.company} ({p.stage}, {amount}, {p.year})")
    return "\n".join(lines)


def generate_objections(
    deck: Deck, scores: list[SectionScore], benchmark: Benchmark | None, llm: LLMClient
) -> list[Objection]:
    prompt = wrap_untrusted("analysis", _prompt(deck, scores, benchmark))
    result = llm.generate_structured(_SYSTEM, prompt, _Objections)
    return result.objections[:_MAX_OBJECTIONS]
