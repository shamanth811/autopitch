"""Analyze a pitch deck PDF from the command line using the real models.

    python scripts/analyze.py examples/acme_grid_deck.pdf --out reports/acme

Writes <out>.json and <out>.md. Requires AUTOPITCH_GEMINI_API_KEY and
AUTOPITCH_LLAMA_API_KEY; add AUTOPITCH_PINECONE_API_KEY to include the benchmark step.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from autopitch.config import get_settings
from autopitch.factory import (
    build_embedder,
    build_extraction_llm,
    build_formd_store,
    build_llama,
    build_ocr,
    build_store,
    embedding_provider,
)
from autopitch.graph import build_graph
from autopitch.parsing import read_slides
from autopitch.report import build_report, render_markdown
from autopitch.tracing import configure_tracing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deck", type=Path)
    parser.add_argument("--out", type=Path, default=None, help="output path without extension")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    s = get_settings()
    missing = [name for name, val in (("LLAMA_API_KEY", s.llama_api_key),) if not val]
    if missing:
        print(f"Missing settings: {', '.join('AUTOPITCH_' + m for m in missing)}", file=sys.stderr)
        return 2

    logging.info("tracing: %s", "on" if configure_tracing(s) else "off")
    embedder = store = None
    if s.pinecone_api_key and embedding_provider(s):
        embedder, store = build_embedder(s), build_store(s)
    else:
        logging.warning("no Pinecone or embedding key: skipping the benchmark step")

    slides = read_slides(args.deck.read_bytes(), max_pages=s.max_pages, ocr=build_ocr(s))
    graph = build_graph(
        build_extraction_llm(s),
        build_llama(s),
        embedder,
        store,
        build_formd_store(s),
        s.sector_classifier,
    )
    report = build_report(
        graph.invoke({"slides": slides}, {"max_concurrency": s.scoring_concurrency})
    )

    out = args.out or args.deck.with_suffix("")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    out.with_suffix(".md").write_text(render_markdown(report), encoding="utf-8")
    logging.info("wrote %s.json and %s.md (composite %s/10)", out, out, report.composite.score)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
