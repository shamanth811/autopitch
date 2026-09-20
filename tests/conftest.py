from __future__ import annotations

import io

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

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


def make_pdf(pages: list[str]) -> bytes:
    """Build a small text PDF with no external tooling."""
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        safe = text.replace("(", "[").replace(")", "]")
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 14 Tf 50 700 Td ({safe}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
        )
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


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
