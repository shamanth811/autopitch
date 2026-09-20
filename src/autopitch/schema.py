"""Typed data model shared by every stage of the pipeline."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class Section(StrEnum):
    PROBLEM = "problem"
    MARKET = "market"
    TRACTION = "traction"
    TEAM = "team"
    MOAT = "moat"
    FINANCIALS = "financials"


class _NullTolerant(BaseModel):
    """Extraction models often answer null for a field the deck does not state, including
    fields that are plain strings or lists. Treat null as absent so the default applies,
    instead of failing validation and burning a retry."""

    @model_validator(mode="before")
    @classmethod
    def _drop_nulls(cls, data):
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


class Slide(BaseModel):
    number: int = Field(ge=1)
    text: str


class Founder(_NullTolerant):
    name: str
    role: str | None = None
    background: str | None = None


class ProblemSection(_NullTolerant):
    statement: str = ""
    target_customer: str | None = None
    evidence: list[str] = Field(default_factory=list)


class MarketSection(_NullTolerant):
    tam_usd: float | None = Field(default=None, description="Total addressable market in USD")
    sam_usd: float | None = None
    som_usd: float | None = None
    methodology: str | None = Field(default=None, description="top-down, bottom-up or unstated")
    sources: list[str] = Field(default_factory=list)


class TractionSection(_NullTolerant):
    arr_usd: float | None = None
    mrr_usd: float | None = None
    monthly_growth_pct: float | None = None
    customers: int | None = None
    retention_pct: float | None = None
    highlights: list[str] = Field(default_factory=list)


class TeamSection(_NullTolerant):
    founders: list[Founder] = Field(default_factory=list)
    headcount: int | None = None
    key_hires: list[str] = Field(default_factory=list)


class MoatSection(_NullTolerant):
    claims: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)
    defensibility: str | None = None


class FinancialsSection(_NullTolerant):
    raise_amount_usd: float | None = None
    valuation_usd: float | None = None
    burn_usd_monthly: float | None = None
    runway_months: float | None = None
    gross_margin_pct: float | None = None
    use_of_funds: list[str] = Field(default_factory=list)


class Deck(_NullTolerant):
    """A pitch deck after structured extraction."""

    company: str
    sector: str = "unknown"
    stage: str | None = Field(default=None, description="e.g. pre-seed, seed, series-a")
    one_liner: str | None = None
    problem: ProblemSection = Field(default_factory=ProblemSection)
    market: MarketSection = Field(default_factory=MarketSection)
    traction: TractionSection = Field(default_factory=TractionSection)
    team: TeamSection = Field(default_factory=TeamSection)
    moat: MoatSection = Field(default_factory=MoatSection)
    financials: FinancialsSection = Field(default_factory=FinancialsSection)


class CriterionScore(BaseModel):
    criterion: str
    score: float = Field(ge=0, le=10)
    reasoning: str = Field(description="Why this score, citing deck content")


class SectionScore(BaseModel):
    section: Section
    score: float = Field(ge=0, le=10)
    criteria: list[CriterionScore]
    summary: str = ""
    missing_data: list[str] = Field(default_factory=list)


class TraceLine(BaseModel):
    """One criterion's path into the composite score."""

    section: Section
    criterion: str
    score: float
    effective_weight: float = Field(description="Section weight split across its criteria")
    reasoning: str


class Composite(BaseModel):
    score: float = Field(ge=0, le=10)
    weights: dict[Section, float]
    contributions: dict[Section, float]
    excluded: list[Section] = Field(default_factory=list)
    trace: list[TraceLine] = Field(default_factory=list)
