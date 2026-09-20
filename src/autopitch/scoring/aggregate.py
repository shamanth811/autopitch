"""Combine section scores into a weighted composite with a per-criterion trace."""

from __future__ import annotations

from autopitch.schema import Composite, Section, SectionScore, TraceLine
from autopitch.scoring.rubric import weights_for


def compose(scores: list[SectionScore], stage: str | None) -> Composite:
    """Weighted mean of section scores.

    Sections the scorer could not evaluate at all (no valid criteria) are excluded and the
    remaining weights are renormalised, so a scoring failure never silently drags the
    composite towards zero. Exclusions are reported on the result.
    """
    base = weights_for(stage)
    by_section = {s.section: s for s in scores}
    scored = {sec: s for sec, s in by_section.items() if s.criteria}
    excluded = [sec for sec in Section if sec not in scored]

    total = sum(base[sec] for sec in scored)
    if total == 0:
        return Composite(score=0.0, weights={}, contributions={}, excluded=excluded)

    weights = {sec: base[sec] / total for sec in scored}
    contributions = {sec: round(scored[sec].score * w, 3) for sec, w in weights.items()}

    trace = [
        TraceLine(
            section=sec,
            criterion=c.criterion,
            score=c.score,
            effective_weight=round(weights[sec] / len(scored[sec].criteria), 4),
            reasoning=c.reasoning,
        )
        for sec in Section
        if sec in scored
        for c in scored[sec].criteria
    ]
    return Composite(
        score=round(sum(contributions.values()), 2),
        weights=weights,
        contributions=contributions,
        excluded=excluded,
        trace=trace,
    )
