import csv
import io
import zipfile

import pytest

from autopitch.graph import build_graph
from autopitch.llm.fake import FakeLLM
from autopitch.objections import _Objections
from autopitch.retrieval import HashEmbedder, InMemoryStore
from autopitch.retrieval.benchmark import Benchmark, benchmark_deck
from autopitch.retrieval.formd import (
    FormDRound,
    FormDStore,
    benchmark_formd,
    industries_for,
    parse_quarter,
)
from autopitch.schema import CriterionScore, Deck, Section
from autopitch.scoring import CRITERIA
from autopitch.scoring.nodes import _SectionJudgement

OFFERING = [
    "ACCESSIONNUMBER", "INDUSTRYGROUPTYPE", "INVESTMENTFUNDTYPE", "ISPOOLEDINVESTMENTFUNDTYPE",
    "ISAMENDMENT", "PREVIOUSACCESSIONNUMBER", "ISEQUITYTYPE", "ISDEBTTYPE", "TOTALOFFERINGAMOUNT",
    "TOTALAMOUNTSOLD", "TOTALNUMBERALREADYINVESTED", "REVENUERANGE",
]  # fmt: skip
ISSUERS = [
    "ACCESSIONNUMBER", "IS_PRIMARYISSUER_FLAG", "CIK", "ENTITYNAME", "ENTITYTYPE",
    "YEAROFINC_TIMESPAN_CHOICE",
]  # fmt: skip
SUBMISSION = ["ACCESSIONNUMBER", "FILING_DATE", "TESTORLIVE"]


def _row(acc, **kw):
    """One filing that passes every filter, with overrides to break one rule at a time."""
    o = dict(
        ACCESSIONNUMBER=acc, INDUSTRYGROUPTYPE="Other Technology", INVESTMENTFUNDTYPE="",
        ISPOOLEDINVESTMENTFUNDTYPE="", ISAMENDMENT="false", PREVIOUSACCESSIONNUMBER="",
        ISEQUITYTYPE="true", ISDEBTTYPE="", TOTALOFFERINGAMOUNT="5000000",
        TOTALAMOUNTSOLD="2000000", TOTALNUMBERALREADYINVESTED="12", REVENUERANGE="No Revenues",
    )  # fmt: skip
    i = dict(
        ACCESSIONNUMBER=acc, IS_PRIMARYISSUER_FLAG="YES", CIK="0000001", ENTITYNAME=f"Co {acc}",
        ENTITYTYPE="Corporation", YEAROFINC_TIMESPAN_CHOICE="withinFiveYears",
    )  # fmt: skip
    s = dict(ACCESSIONNUMBER=acc, FILING_DATE="15-AUG-2025", TESTORLIVE="LIVE")
    for key, value in kw.items():
        for d in (o, i, s):
            if key in d:
                d[key] = value
    return o, i, s


def _zip(*rows) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, cols, idx in (
            ("OFFERING.tsv", OFFERING, 0),
            ("ISSUERS.tsv", ISSUERS, 1),
            ("FORMDSUBMISSION.tsv", SUBMISSION, 2),
        ):
            out = io.StringIO()
            w = csv.DictWriter(out, fieldnames=cols, delimiter="\t")
            w.writeheader()
            w.writerows(r[idx] for r in rows)
            z.writestr(f"2025Q3_d/{name}", out.getvalue())
    return buf.getvalue()


def test_a_normal_startup_raise_is_kept_and_typed():
    (r,) = parse_quarter(_zip(_row("A1")))
    assert r.company == "Co A1" and r.industry == "Other Technology"
    assert r.amount_sold_usd == 2_000_000 and r.offering_usd == 5_000_000
    assert r.investors == 12 and r.revenue_range == "No Revenues" and r.filed == "2025-08-15"


@pytest.mark.parametrize(
    "override",
    [
        {"INDUSTRYGROUPTYPE": "Pooled Investment Fund"},
        {"INDUSTRYGROUPTYPE": "Other Real Estate"},
        {"INVESTMENTFUNDTYPE": "Venture Capital Fund"},
        {"ENTITYTYPE": "Limited Partnership"},
        {"YEAROFINC_TIMESPAN_CHOICE": "overFiveYears"},
        {"ISEQUITYTYPE": "", "ISDEBTTYPE": "true"},
        {"ISDEBTTYPE": "true"},
        {"TOTALAMOUNTSOLD": "0"},
        {"TOTALAMOUNTSOLD": "1000"},
        {"TOTALAMOUNTSOLD": "Indefinite"},
        {"TESTORLIVE": "TEST"},
        {"IS_PRIMARYISSUER_FLAG": "NO"},
        {"FILING_DATE": "not a date"},
    ],
)
def test_filters_drop_things_that_are_not_startup_raises(override):
    assert parse_quarter(_zip(_row("A1", **override))) == []


def test_an_amendment_supersedes_the_filing_it_restates():
    original = _row("A1", TOTALAMOUNTSOLD="1000000")
    amended = _row(
        "A2", ISAMENDMENT="true", PREVIOUSACCESSIONNUMBER="A1", TOTALAMOUNTSOLD="3000000"
    )
    rounds = parse_quarter(_zip(original, amended))
    assert [r.accession for r in rounds] == ["A2"]
    assert rounds[0].amount_sold_usd == 3_000_000


def test_undisclosed_revenue_is_not_kept_as_a_range():
    (r,) = parse_quarter(_zip(_row("A1", REVENUERANGE="Decline to Disclose")))
    assert r.revenue_range is None


@pytest.mark.parametrize(
    ("sector", "first", "recognised"),
    [
        ("biotech", "Biotechnology", True),
        ("Healthtech", "Other Health Care", True),
        ("fintech", "Other Banking and Financial Services", True),
        ("climate tech", "Other Energy", True),
        ("saas", "Other Technology", True),
        ("AI infrastructure", "Other Technology", True),
        ("retail", "Retailing", True),  # "ai" inside "retail" must not send it to tech
        ("consumer marketplace", "Retailing", True),
        ("underwater basket weaving", "Other Technology", False),
        ("unknown", "Other Technology", False),
    ],
)
def test_sector_mapping(sector, first, recognised):
    groups, ok = industries_for(sector)
    assert groups[0] == first and ok is recognised


def _store(amounts, industry="Other Energy") -> FormDStore:
    store = FormDStore(":memory:")
    store.upsert(
        [
            FormDRound(
                accession=f"a{i}", company=f"c{i}", cik=str(i), industry=industry,
                amount_sold_usd=a, filed="2025-06-01",
            )
            for i, a in enumerate(amounts)
        ]
    )  # fmt: skip
    return store


def test_percentile_and_quartiles(sample_deck):
    # 100 raises of $1M..$100M in $1M steps; the deck (climate) asks for $3M.
    stats = benchmark_formd(sample_deck, _store([i * 1e6 for i in range(1, 101)]))
    assert stats.peers == 100 and stats.industries[0] == "Other Energy"
    assert stats.median_usd == pytest.approx(50.5e6)
    assert stats.p25_usd == pytest.approx(25.75e6)
    assert stats.ask_percentile == 3.0
    assert any("smaller than 97%" in f for f in stats.flags)
    assert stats.period_start == stats.period_end == "2025-06-01"


def test_a_very_large_ask_is_flagged(sample_deck):
    sample_deck.financials.raise_amount_usd = 95e6
    stats = benchmark_formd(sample_deck, _store([i * 1e6 for i in range(1, 101)]))
    assert stats.ask_percentile == 95.0
    assert any("larger than 95%" in f for f in stats.flags)


def test_a_typical_ask_raises_no_flag(sample_deck):
    sample_deck.financials.raise_amount_usd = 40e6
    assert benchmark_formd(sample_deck, _store([i * 1e6 for i in range(1, 101)])).flags == []


def test_too_few_peers_gives_no_distribution(sample_deck):
    stats = benchmark_formd(sample_deck, _store([1e6] * 5))
    assert stats.peers == 5 and stats.median_usd is None and stats.ask_percentile is None
    assert any("too few" in f for f in stats.flags)


def test_missing_ask_still_reports_the_distribution(sample_deck):
    sample_deck.financials.raise_amount_usd = None
    stats = benchmark_formd(sample_deck, _store([i * 1e6 for i in range(1, 101)]))
    assert stats.median_usd and stats.ask_percentile is None
    assert any("does not state a raise" in f for f in stats.flags)


def test_unrecognised_sector_is_disclosed(sample_deck):
    sample_deck.sector = "underwater basket weaving"
    stats = benchmark_formd(
        sample_deck, _store([i * 1e6 for i in range(1, 101)], industry="Other Technology")
    )
    assert stats.sector_recognised is False and any("not recognised" in f for f in stats.flags)


def test_empty_store_means_no_benchmark(sample_deck):
    assert benchmark_formd(sample_deck, FormDStore(":memory:")) is None


def test_upsert_replaces_by_filing():
    store = _store([1e6])
    store.upsert([FormDRound(accession="a0", company="c0", cik="0", industry="Other Energy",
                             amount_sold_usd=9e6, filed="2025-06-01")])  # fmt: skip
    assert store.amounts(("Other Energy",)) == [9e6]
    assert store.industry_counts() == [("Other Energy", 1)]


# --- S-1 benchmark changes -------------------------------------------------------------------


def test_one_company_cannot_fill_the_comparables(sample_deck):
    from autopitch.retrieval import FundingPattern, pattern_text

    patterns = [
        FundingPattern(id=f"p{i}", company="Same Co", sector="climate", stage="seed",
                       round_amount_usd=1e6, year=2020, summary="grid software")
        for i in range(6)
    ]  # fmt: skip
    emb, store = HashEmbedder(), InMemoryStore()
    store.upsert(patterns, emb.embed_documents([pattern_text(p) for p in patterns]))
    result = benchmark_deck(sample_deck, emb, store)
    assert len(result.comparables) == 2


def test_median_needs_three_same_stage_comparables(sample_deck):
    from autopitch.retrieval import FundingPattern, pattern_text

    patterns = [
        FundingPattern(id=f"p{i}", company=f"co{i}", sector="climate", stage="seed",
                       round_amount_usd=1e6, year=2020, summary="grid software")
        for i in range(2)
    ]  # fmt: skip
    emb, store = HashEmbedder(), InMemoryStore()
    store.upsert(patterns, emb.embed_documents([pattern_text(p) for p in patterns]))
    result = benchmark_deck(sample_deck, emb, store)
    assert result.median_raise_usd is None and result.raise_ratio is None
    assert any("too few for a median" in f for f in result.flags)


# --- graph wiring ---------------------------------------------------------------------------


def _graph(sample_deck, **kw):
    def judge(system, prompt):
        section = next(s for s in Section if f"Section under review: {s.value}" in prompt)
        return _SectionJudgement(
            criteria=[
                CriterionScore(criterion=n, score=7, reasoning="ok") for n in CRITERIA[section]
            ],
            summary="fine",
        )

    return build_graph(
        FakeLLM({Deck: sample_deck, _Objections: _Objections(objections=[])}),
        FakeLLM({_SectionJudgement: judge}),
        **kw,
    )


def test_graph_uses_form_d_alone_when_there_is_no_embedding_index(sample_deck):
    state = _graph(sample_deck, formd_store=_store([i * 1e6 for i in range(1, 101)])).invoke(
        {"slides": []}
    )
    bench = state["benchmark"]
    assert isinstance(bench, Benchmark) and bench.comparables == []
    assert bench.formd.peers == 100 and bench.formd.ask_percentile == 3.0


def test_graph_skips_the_benchmark_with_no_sources(sample_deck):
    assert "benchmark" not in _graph(sample_deck).invoke({"slides": []})


def test_every_extractor_sector_label_is_recognised_by_the_benchmark():
    from autopitch.parsing.extract import SECTORS

    for label in SECTORS:
        _, recognised = industries_for(label)
        assert recognised, f"sector '{label}' has no Form D mapping"


def test_extraction_prompt_lists_the_sector_vocabulary():
    from autopitch.parsing.extract import _SYSTEM, SECTORS

    assert all(label in _SYSTEM for label in SECTORS)


def test_agtech_maps_to_agriculture_not_generic_tech():
    assert industries_for("agtech")[0] == ("Agriculture",)


def test_dissimilar_matches_are_dropped_not_shown(sample_deck):
    from autopitch.retrieval import FundingPattern, pattern_text

    p = FundingPattern(
        id="p",
        company="Unrelated Co",
        sector="climate",
        stage="seed",
        round_amount_usd=1e6,
        year=2020,
        summary="zebra crossing paint marketing",
    )
    emb, store = HashEmbedder(), InMemoryStore()
    store.upsert([p], emb.embed_documents([pattern_text(p)]))
    strict = benchmark_deck(sample_deck, emb, store, min_similarity=0.99)
    assert strict.comparables == []
    assert any("No sufficiently similar" in f for f in strict.flags)
    assert benchmark_deck(sample_deck, emb, store, min_similarity=0.0).comparables
