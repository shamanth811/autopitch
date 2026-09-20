import pytest

from autopitch.retrieval import FundingPattern, HashEmbedder, InMemoryStore, pattern_text
from autopitch.retrieval.benchmark import benchmark_deck


def _store(*rows: tuple[str, str, str, float | None]) -> tuple[InMemoryStore, HashEmbedder]:
    patterns = [
        FundingPattern(
            id=f"p{i}",
            company=f"co{i}",
            sector=sector,
            stage=stage,
            round_amount_usd=amt,
            year=2020,
            summary="grid software for commercial buildings",
        )
        for i, (sector, stage, _, amt) in enumerate(rows)
    ]
    emb = HashEmbedder()
    store = InMemoryStore()
    store.upsert(patterns, emb.embed_documents([pattern_text(p) for p in patterns]))
    return store, emb


def test_ratio_uses_median_of_same_stage_comparables(sample_deck):
    store, emb = _store(
        ("climate", "seed", "", 1e6),
        ("climate", "seed", "", 2e6),
        ("climate", "seed", "", 3e6),
        ("climate", "series-a", "", 50e6),
    )
    result = benchmark_deck(sample_deck, emb, store)  # deck raises 3M, seed
    assert result.stage_comparables == 3
    assert result.median_raise_usd == 2e6
    assert result.raise_ratio == pytest.approx(1.5)
    assert result.flags == []


def test_high_ask_is_flagged(sample_deck):
    store, emb = _store(*[("climate", "seed", "", 1e6)] * 3)
    result = benchmark_deck(sample_deck, emb, store)
    assert result.raise_ratio == 3.0
    assert any("3.0x the median" in f for f in result.flags)


def test_sparse_sector_widens_search_and_says_so(sample_deck):
    store, emb = _store(
        ("fintech", "seed", "", 2e6),
        ("fintech", "seed", "", 2e6),
        ("fintech", "seed", "", 2e6),
        ("climate", "seed", "", 2e6),
    )
    result = benchmark_deck(sample_deck, emb, store)
    assert result.sector_matched is False
    assert any("comparables below span other sectors" in f for f in result.flags)


def test_empty_index_yields_flag_not_crash(sample_deck):
    result = benchmark_deck(sample_deck, HashEmbedder(), InMemoryStore())
    assert result.comparables == [] and result.raise_ratio is None
    assert result.flags


def test_missing_ask_is_reported(sample_deck):
    sample_deck.financials.raise_amount_usd = None
    store, emb = _store(*[("climate", "seed", "", 1e6)] * 3)
    result = benchmark_deck(sample_deck, emb, store)
    assert result.median_raise_usd == 1e6 and result.raise_ratio is None
    assert any("does not state a raise" in f for f in result.flags)
