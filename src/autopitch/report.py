"""Assemble the final report from graph output and render it as JSON or Markdown."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from autopitch import __version__
from autopitch.objections import Objection
from autopitch.retrieval.benchmark import Benchmark
from autopitch.schema import Composite, Deck, Section, SectionScore

DISCLAIMER = (
    "Scores are model-generated from the text of the uploaded deck and a rubric. They are a "
    "screening aid, not investment advice, and reflect only what the deck states."
)


class Report(BaseModel):
    version: str = __version__
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    deck: Deck
    composite: Composite
    sections: list[SectionScore]
    weak_sections: list[Section]
    benchmark: Benchmark | None = None
    objections: list[Objection] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER


def build_report(state: dict) -> Report:
    order = {sec: i for i, sec in enumerate(Section)}
    return Report(
        deck=state["deck"],
        composite=state["composite"],
        sections=sorted(state["scores"], key=lambda s: order[s.section]),
        weak_sections=state.get("weak_sections", []),
        benchmark=state.get("benchmark"),
        objections=state.get("objections", []),
    )


def _usd(v: float | None) -> str:
    return f"${v:,.0f}" if v else "n/a"


def render_markdown(r: Report) -> str:
    d, c = r.deck, r.composite
    out = [
        f"# Pitch analysis: {d.company}",
        "",
        f"Sector: **{d.sector}** | Stage: **{d.stage or 'unknown'}** | "
        f"Composite score: **{c.score}/10**",
        "",
        "## Section scores",
        "",
        "| Section | Score | Weight | Verdict |",
        "|---|---:|---:|---|",
    ]
    for s in r.sections:
        w = c.weights.get(s.section)
        weight = f"{w:.0%}" if w is not None else "excluded"
        flag = " (weak)" if s.section in r.weak_sections else ""
        out.append(f"| {s.section.value}{flag} | {s.score} | {weight} | {s.summary} |")

    out += ["", "## Reasoning trace", ""]
    for s in r.sections:
        out.append(f"### {s.section.value.capitalize()} ({s.score}/10)")
        out.extend(f"- **{cr.criterion}** {cr.score}/10: {cr.reasoning}" for cr in s.criteria)
        out.extend(f"- _Missing:_ {m}" for m in s.missing_data)
        out.append("")

    if r.benchmark and r.benchmark.formd:
        f = r.benchmark.formd
        out += ["## Raise size against SEC Form D filings", ""]
        if f.median_usd is not None:
            place = (
                f" Ask of {_usd(d.financials.raise_amount_usd)} sits at the "
                f"{f.ask_percentile:.0f}th percentile."
                if f.ask_percentile is not None
                else ""
            )
            out.append(
                f"{f.peers:,} private raises by companies under five years old "
                f"({', '.join(f.industries)}), filed {f.period_start} to {f.period_end}: "
                f"25th percentile {_usd(f.p25_usd)}, median {_usd(f.median_usd)}, "
                f"75th percentile {_usd(f.p75_usd)}, 90th percentile {_usd(f.p90_usd)}.{place}"
            )
            out.append("")
        out.extend(f"- {flag}" for flag in f.flags)
        out += [
            "",
            "_Form D lists the amount sold so far and has no funding stage, so this compares "
            "size only, across all stages._",
            "",
        ]

    if r.benchmark and (r.benchmark.comparables or r.benchmark.flags):
        b = r.benchmark
        out += [
            "## Similar companies in SEC S-1 filings",
            "",
            f"Comparables retrieved: {len(b.comparables)} | Same-stage with amount: "
            f"{b.stage_comparables} | Median raise: {_usd(b.median_raise_usd)} | "
            f"Deck ask: {_usd(d.financials.raise_amount_usd)}",
            "",
        ]
        out.extend(f"- {f}" for f in b.flags)
        out.append("")
        out.append("| Company | Stage | Amount | Year | Similarity |")
        out.append("|---|---|---:|---:|---:|")
        for m in b.comparables:
            p = m.pattern
            out.append(
                f"| [{p.company}]({p.source_url}) | {p.stage or 'n/a'} | "
                f"{_usd(p.round_amount_usd)} | {p.year or 'n/a'} | {m.similarity:.2f} |"
            )
        out.append("")

    if r.objections:
        out += ["## Likely investor objections", ""]
        for i, o in enumerate(r.objections, 1):
            out += [
                f"{i}. **{o.question}** ({o.section.value})",
                f"   - Basis: {o.basis}",
                f"   - Bring: {o.suggested_response}",
            ]
        out.append("")

    out += ["---", f"_{r.disclaimer}_", ""]
    return "\n".join(out)
