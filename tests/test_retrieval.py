from autopitch.retrieval import (
    FundingPattern,
    HashEmbedder,
    InMemoryStore,
    deck_query_text,
    pattern_text,
)


def _pattern(id_: str, sector: str, summary: str, amount: float = 5e6) -> FundingPattern:
    return FundingPattern(
        id=id_, company=id_, sector=sector, stage="seed", round_amount_usd=amount,
        year=2021, summary=summary,
    )


def _loaded_store():
    patterns = [
        _pattern("solar-co", "climate", "grid demand response software for buildings"),
        _pattern("bank-co", "fintech", "payments API for small business lending"),
        _pattern("heat-co", "climate", "heat pump financing for homeowners"),
    ]
    emb = HashEmbedder()
    store = InMemoryStore()
    store.upsert(patterns, emb.embed_documents([pattern_text(p) for p in patterns]))
    return store, emb


def test_query_ranks_topically_similar_pattern_first(sample_deck):
    store, emb = _loaded_store()
    matches = store.query(emb.embed_query(deck_query_text(sample_deck)), top_k=3)
    assert matches[0].pattern.id == "solar-co"


def test_sector_filter_excludes_other_sectors(sample_deck):
    store, emb = _loaded_store()
    matches = store.query(emb.embed_query(deck_query_text(sample_deck)), top_k=5, sector="climate")
    assert {m.pattern.sector for m in matches} == {"climate"}


def test_upsert_is_idempotent_by_id():
    store, emb = _loaded_store()
    p = _pattern("solar-co", "climate", "replacement text")
    store.upsert([p], emb.embed_documents([pattern_text(p)]))
    assert len(store.query(emb.embed_query("climate"), top_k=10)) == 3
