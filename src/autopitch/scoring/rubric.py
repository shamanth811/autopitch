"""Scoring rubric: criteria per section and stage-dependent section weights.

Kept as plain data so the rubric can be reviewed and tuned without touching graph code.
"""

from __future__ import annotations

from autopitch.schema import Section

CRITERIA: dict[Section, dict[str, str]] = {
    Section.PROBLEM: {
        "clarity": "Is the problem stated specifically, for a named customer, in one or two sentences?",
        "severity": "Is the pain frequent or costly enough that buyers already spend money or time on it?",
        "evidence": "Is the problem backed by interviews, data or observed customer behaviour rather than assertion?",
    },
    Section.MARKET: {
        "size": "Is the addressable market large enough to support a venture-scale outcome?",
        "methodology": "Is sizing built bottom-up from customers and price, not a top-down slice of a report?",
        "timing": "Does the deck explain why this market is open now?",
    },
    Section.TRACTION: {
        "revenue": "Is there recurring revenue, and is its scale credible for the stated stage?",
        "growth": "Is the growth rate strong and sustained rather than a single spike?",
        "retention": "Do customers stay and expand, or is there evidence of churn?",
    },
    Section.TEAM: {
        "founder_market_fit": "Do the founders have direct experience or insight into this problem?",
        "execution_record": "Has the team shipped, sold or scaled something relevant before?",
        "completeness": "Are the critical roles (technical, commercial) covered?",
    },
    Section.MOAT: {
        "defensibility": "Is there a durable advantage: data, network effects, IP, switching costs, distribution?",
        "competitive_awareness": "Does the deck name real competitors and explain honest differentiation?",
    },
    Section.FINANCIALS: {
        "unit_economics": "Are margins and unit economics healthy and clearly stated?",
        "runway": "Does the raise give enough runway to reach the next milestone?",
        "use_of_funds": "Is use of funds specific and tied to milestones?",
    },
}

# Weights sum to 1.0 per stage. Earlier stages lean on team and problem because there is
# little revenue to judge; later stages lean on traction and financials.
_DEFAULT = {
    Section.PROBLEM: 0.15,
    Section.MARKET: 0.15,
    Section.TRACTION: 0.25,
    Section.TEAM: 0.20,
    Section.MOAT: 0.10,
    Section.FINANCIALS: 0.15,
}

STAGE_WEIGHTS: dict[str, dict[Section, float]] = {
    "pre-seed": {
        Section.PROBLEM: 0.20,
        Section.MARKET: 0.15,
        Section.TRACTION: 0.10,
        Section.TEAM: 0.35,
        Section.MOAT: 0.10,
        Section.FINANCIALS: 0.10,
    },
    "seed": _DEFAULT,
    "series-a": {
        Section.PROBLEM: 0.10,
        Section.MARKET: 0.15,
        Section.TRACTION: 0.30,
        Section.TEAM: 0.15,
        Section.MOAT: 0.10,
        Section.FINANCIALS: 0.20,
    },
}


def weights_for(stage: str | None) -> dict[Section, float]:
    return dict(STAGE_WEIGHTS.get((stage or "").lower(), _DEFAULT))
