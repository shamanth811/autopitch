import pytest

from autopitch.llm.fake import FakeLLM
from autopitch.retrieval import HashEmbedder, InMemoryStore
from autopitch.retrieval.edgar import EdgarClient, FilingRef, html_to_text
from autopitch.retrieval.ingest import (
    _ExtractedRound,
    _ExtractedRounds,
    extract_patterns,
    find_financing_excerpt,
    ingest_filings,
)

REF = FilingRef(
    company="Voltly Inc",
    cik="0001234567",
    accession="0001193125-21-000001",
    document="d1s1.htm",
    form="S-1",
    filed="2021-05-03",
)

FILING = """
TABLE OF CONTENTS
Recent Sales of Unregistered Securities ........ II-2
...
Item 15. Recent Sales of Unregistered Securities
In March 2018 we sold 4,000,000 shares of Series A preferred stock for aggregate proceeds of $8.0 million.
"""


def test_html_to_text_drops_scripts_and_collapses_whitespace():
    html = "<html><head><title>x</title></head><body><script>bad()</script><p>Hello   <b>world</b></p><p>Next</p></body></html>"
    assert html_to_text(html) == "Hello world\nNext"


def test_excerpt_uses_last_marker_not_table_of_contents():
    excerpt = find_financing_excerpt(FILING)
    assert excerpt.startswith("Recent Sales of Unregistered Securities\nIn March 2018")
    assert "II-2" not in excerpt


def test_excerpt_none_when_section_absent():
    assert find_financing_excerpt("nothing relevant here") is None


def test_filing_url_strips_leading_zeros_and_dashes():
    assert REF.url == "https://www.sec.gov/Archives/edgar/data/1234567/000119312521000001/d1s1.htm"


def test_edgar_client_requires_contact_email():
    with pytest.raises(ValueError, match="contact email"):
        EdgarClient("just-a-name")


def _llm():
    return FakeLLM(
        {
            _ExtractedRounds: _ExtractedRounds(
                sector="Climate",
                rounds=[
                    _ExtractedRound(
                        stage="series-a",
                        round_amount_usd=8e6,
                        year=2018,
                        investors=["Fund One"],
                        summary="Series A for grid software.",
                    )
                ],
            )
        }
    )


def test_extract_patterns_builds_stable_ids_and_lowercases_sector():
    patterns = extract_patterns(REF, FILING, _llm())
    assert len(patterns) == 1
    assert patterns[0].id == "0001193125-21-000001-voltly-inc-0"
    assert patterns[0].sector == "climate"
    assert patterns[0].source_url == REF.url


def test_ingest_stores_patterns_and_skips_filings_without_section():
    class StubEdgar:
        def fetch_text(self, ref):
            return FILING if ref.company == "Voltly Inc" else "no financing info"

    other = REF.model_copy(update={"company": "Blank Co", "accession": "0001193125-21-000002"})
    store = InMemoryStore()
    n = ingest_filings([REF, other], StubEdgar(), _llm(), HashEmbedder(), store)
    assert n == 1
    assert len(store.query(HashEmbedder().embed_query("climate"), top_k=10)) == 1
