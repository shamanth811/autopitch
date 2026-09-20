"""Render the JSON produced by docs/deck-generation-prompt.md into PDFs plus an answer key.

    python scripts/build_decks.py decks.json --out examples/generated

Writes <id>.pdf for each company and answer_key.json. Fails loudly on anything that would
make the PDF unreadable to the pipeline (over-long lines, non-ASCII text, empty slides).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from autopitch.testing import make_pdf

MAX_LINE = 95


def problems(company: dict) -> list[str]:
    found = []
    slides = company.get("slides", [])
    if len(slides) != 10:
        found.append(f"expected 10 slides, got {len(slides)}")
    for n, text in enumerate(slides, 1):
        if not text.strip():
            found.append(f"slide {n} is empty")
        if not text.isascii():
            found.append(f"slide {n} has non-ASCII characters")
        for line in text.split("\n"):
            if len(line) > MAX_LINE:
                found.append(f"slide {n}: line is {len(line)} chars ({line[:40]}...)")
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decks", type=Path)
    parser.add_argument("--out", type=Path, default=Path("examples/generated"))
    args = parser.parse_args()

    data = json.loads(args.decks.read_text(encoding="utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)
    key, bad = {}, 0
    for company in data["companies"]:
        issues = problems(company)
        if issues:
            bad += 1
            print(f"{company.get('id', '?')}: " + "; ".join(issues), file=sys.stderr)
            continue
        path = args.out / f"{company['id']}.pdf"
        path.write_bytes(make_pdf(company["slides"]))
        key[company["id"]] = {
            "company": company["company"],
            "sector": company["sector"],
            "stage": company["stage"],
            **company["answer_key"],
            "sources": company.get("sources", []),
            "comparable_rounds": company.get("comparable_rounds", []),
        }
        print(f"wrote {path}")
    (args.out / "answer_key.json").write_text(json.dumps(key, indent=2), encoding="utf-8")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
