"""Build the Pinecone index of funding patterns from SEC S-1 filings.

    python scripts/ingest_filings.py --query "Series A preferred stock" --limit 25

Requires AUTOPITCH_GEMINI_API_KEY, AUTOPITCH_PINECONE_API_KEY and AUTOPITCH_SEC_USER_AGENT.
"""

from __future__ import annotations

import argparse
import logging

from autopitch.config import get_settings
from autopitch.factory import build_embedder, build_gemini, build_store
from autopitch.retrieval.edgar import EdgarClient
from autopitch.retrieval.ingest import ingest_filings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default='"Series A preferred stock" "venture"')
    parser.add_argument("--forms", default="S-1")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    edgar = EdgarClient(settings.sec_user_agent)

    refs = edgar.search(args.query, args.forms, args.start, args.end, args.limit)
    logging.info("found %d filings", len(refs))
    stored = ingest_filings(
        refs, edgar, build_gemini(settings), build_embedder(settings), build_store(settings)
    )
    logging.info("done: %d funding patterns stored in %s", stored, settings.pinecone_index)


if __name__ == "__main__":
    main()
