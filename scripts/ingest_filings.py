"""Build the Pinecone index of funding patterns from SEC S-1 filings.

    python scripts/ingest_filings.py --query "Series A preferred stock" --limit 25

Requires AUTOPITCH_LLAMA_API_KEY (or a Gemini key) for extraction, AUTOPITCH_VOYAGE_API_KEY
(or a Gemini key) for embeddings, AUTOPITCH_PINECONE_API_KEY and AUTOPITCH_SEC_USER_AGENT.
"""

from __future__ import annotations

import argparse
import logging

import httpx

from autopitch.config import get_settings
from autopitch.factory import build_embedder, build_extraction_llm, build_store
from autopitch.retrieval.edgar import EdgarClient
from autopitch.retrieval.ingest import ingest_filings

DEFAULT_QUERIES = [
    '"Series A preferred stock" software subscription',
    '"Series B preferred stock" fintech payments',
    '"convertible preferred stock" biotechnology clinical',
    '"Series A preferred stock" climate energy',
    '"Series B preferred stock" marketplace consumer',
    '"convertible preferred stock" cybersecurity',
    '"Series A preferred stock" healthcare technology',
    '"Series C preferred stock" artificial intelligence',
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--query",
        action="append",
        help="EDGAR full-text query; repeat for several. Defaults to a spread of sectors.",
    )
    parser.add_argument("--forms", default="S-1")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--limit", type=int, default=6, help="Filings per query")
    parser.add_argument(
        "--excerpt-chars",
        type=int,
        help="Filing text sent to the model per filing. Default 30000 with Gemini, 10000 "
        "otherwise so one request fits a free-tier Groq token-per-minute cap.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    edgar = EdgarClient(settings.sec_user_agent)
    excerpt_chars = args.excerpt_chars or (30_000 if settings.gemini_api_key else 10_000)
    embedder = build_embedder(settings)
    if embedder is None:
        raise SystemExit("Set AUTOPITCH_VOYAGE_API_KEY (or a Gemini key) to embed filings.")

    refs: dict[str, object] = {}
    for query in args.query or DEFAULT_QUERIES:
        try:
            found = edgar.search(query, args.forms, args.start, args.end, args.limit)
        except httpx.HTTPError as exc:  # one failed query must not cost the whole run
            logging.warning("search failed for %r, skipping: %s", query, exc)
            continue
        for ref in found:
            refs.setdefault(ref.accession, ref)
    refs = list(refs.values())
    logging.info("found %d filings", len(refs))
    stored = ingest_filings(
        refs,
        edgar,
        build_extraction_llm(settings),
        embedder,
        build_store(settings),
        excerpt_chars,
    )
    logging.info("done: %d funding patterns stored in %s", stored, settings.pinecone_index)


if __name__ == "__main__":
    main()
