from __future__ import annotations

import pytest

from autopitch.schema import (
    Deck,
    FinancialsSection,
    Founder,
    MarketSection,
    MoatSection,
    ProblemSection,
    TeamSection,
    TractionSection,
)


@pytest.fixture
def sample_deck() -> Deck:
    return Deck(
        company="Acme Grid",
        sector="climate",
        stage="seed",
        one_liner="Demand-response software for commercial buildings",
        problem=ProblemSection(
            statement="Commercial buildings waste 30% of energy at peak load",
            target_customer="Facility managers",
            evidence=["12 pilot interviews"],
        ),
        market=MarketSection(tam_usd=8e9, sam_usd=1.2e9, som_usd=60e6, methodology="bottom-up"),
        traction=TractionSection(arr_usd=420_000, monthly_growth_pct=9, customers=14),
        team=TeamSection(
            founders=[Founder(name="A. Rao", role="CEO", background="ex-Tesla Energy")],
            headcount=7,
        ),
        moat=MoatSection(claims=["Proprietary load-forecast model"], competitors=["Enel X"]),
        financials=FinancialsSection(
            raise_amount_usd=3e6, burn_usd_monthly=110_000, runway_months=14, gross_margin_pct=68
        ),
    )
