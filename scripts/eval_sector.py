"""Measure sector-classification accuracy and stability against a hand-labelled set.

    python scripts/eval_sector.py --repeats 2

Each case is a short, fictional deck. `label` is the sector a reasonable investor would give;
`also` lists labels that are defensible for the same company. Strict accuracy counts only
`label`; lenient accuracy also counts `also` and any label that maps to the same SEC Form D
industry groups (climate and energy, for example), because that is what the benchmark uses.

The cases were written by the person who wrote the classifier, so they flatter it. Treat the
result as a regression check and a comparison against the baseline, not a real-world accuracy.
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter

from autopitch.config import get_settings
from autopitch.factory import build_extraction_llm
from autopitch.parsing.extract import _summary, extract_deck, resolve_sector
from autopitch.parsing.sector import classify_sector
from autopitch.retrieval.formd import industries_for
from autopitch.schema import Slide

# (label, also-acceptable, slides). The decks deliberately avoid naming their sector.
CASES: list[tuple[str, tuple[str, ...], list[str]]] = [
    ("climate", ("energy",), [
        "Acme Grid\nDemand-response software for commercial buildings\nSeed | Raising $3M",
        "Buildings waste 30% of energy at peak load. Facility managers cannot shed load automatically.",
    ]),
    ("saas", (), [
        "Ledgerly\nAutomated month-end close for mid-market finance teams\nSeed | $4M",
        "Controllers spend 8 days closing the books. We sell per-seat subscriptions to CFO offices.",
    ]),
    ("ai", ("devtools",), [
        "Cortexa\nA foundation model for legal reasoning, served by API\nSeed | $6M",
        "We train and host large language models; customers pay per token for inference.",
    ]),
    ("cybersecurity", (), [
        "Vaultline\nStops credential theft before attackers move laterally\nSeed | $5M",
        "Security teams drown in alerts. Our agent detects stolen sessions and isolates hosts.",
    ]),
    ("fintech", (), [
        "PayBridge\nCross-border payouts for freelancers and marketplaces\nSeed | $3M",
        "We charge 0.8% on payment volume and hold licences in 14 countries.",
    ]),
    ("healthtech", (), [
        "Clinara\nAutomates prior authorisation for hospital billing teams\nSeed | $4M",
        "Hospitals lose weeks to insurer paperwork. Our software submits and tracks each claim.",
    ]),
    ("biotech", (), [
        "Nuvora Therapeutics\nA small-molecule treatment for fibrosis\nSeed | $12M",
        "Preclinical data show a 60% reduction in scarring. IND filing planned in 18 months.",
    ]),
    ("energy", ("climate",), [
        "Voltcell\nLong-duration grid batteries using iron chemistry\nSeries A | $20M",
        "Utilities need storage that lasts 100 hours. Our cells cost half of lithium-ion per kWh.",
    ]),
    ("marketplace", (), [
        "Fixably\nOn-demand home repair, matched to vetted local contractors\nSeed | $3M",
        "Homeowners cannot find reliable tradespeople. We take 18% of every job booked.",
    ]),
    ("consumer", (), [
        "Sipwell\nFunctional sparkling drinks sold in grocery and online\nSeed | $2M",
        "Shoppers want less sugar. Our brand is in 900 stores and sells to consumers directly.",
    ]),
    ("hardware", (), [
        "Robolift\nWarehouse robots that unload trucks\nSeries A | $15M",
        "Loading docks are the last manual step. Each robot replaces three workers.",
    ]),
    ("devtools", (), [
        "Trace.io\nObservability for microservice deployments\nSeed | $5M",
        "Engineers spend hours debugging production. Our SDK traces requests across services.",
    ]),
    ("agtech", (), [
        "Fieldwise\nSoil sensors and yield forecasting for row-crop farms\nSeed | $3M",
        "Farmers over-apply fertiliser. We tell them exactly where and when.",
    ]),
    ("telecom", (), [
        "Skylink\nLow-cost satellite broadband for rural regions\nSeries A | $25M",
        "Two billion people lack reliable connectivity. Our terminals cost $90.",
    ]),
    # Deliberately hard: technology used vs product sold.
    ("saas", (), [
        "Routewise\nRoute optimisation for delivery fleets, powered by machine learning\nSeed | $4M",
        "Fleet managers cut fuel costs 15%. We sell annual subscriptions to logistics companies.",
    ]),
    ("healthtech", (), [
        "Pulsecare\nRemote patient monitoring for chronic-heart-failure clinics\nSeed | $5M",
        "Clinics reduce readmissions with our wearable and dashboard, billed to insurers.",
    ]),
    ("fintech", ("saas",), [
        "Taxpilot\nAutomated sales-tax compliance for online retailers\nSeed | $4M",
        "Merchants file in 40 states. We calculate, collect and remit tax through an API.",
    ]),
    ("climate", (), [
        "Carbonly\nCarbon accounting for supply chains\nSeed | $3M",
        "Companies must report Scope 3 emissions. Our platform measures them from invoices.",
    ]),
    ("ai", ("saas",), [
        "Agentflow\nAutonomous AI agents that resolve customer support tickets\nSeed | $6M",
        "Our agents handle 70% of tickets end to end, priced per resolved conversation.",
    ]),
    ("hardware", (), [
        "Chiplet Labs\nEnergy-efficient inference chips for data centres\nSeries A | $30M",
        "GPUs waste power. Our custom silicon delivers 4x performance per watt.",
    ]),
]  # fmt: skip


def _same_benchmark(a: str, b: str) -> bool:
    return industries_for(a)[0] == industries_for(b)[0]


def _score(results: dict[int, list[str]]) -> tuple[float, float, float]:
    strict = lenient = stable = total = 0
    for i, got in results.items():
        label, also, _ = CASES[i]
        for g in got:
            total += 1
            strict += g == label
            lenient += g == label or g in also or _same_benchmark(g, label)
        stable += len(set(got)) == 1
    return strict / total, lenient / total, stable / len(results)


def _misses(results: dict[int, list[str]]) -> list[str]:
    return [
        f"  want {CASES[i][0]:13} got {dict(Counter(got))}  ({CASES[i][2][0].splitlines()[0]})"
        for i, got in results.items()
        if any(g != CASES[i][0] for g in got)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=2, help="Extractions per deck")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    llm = build_extraction_llm(get_settings())
    baseline: dict[int, list[str]] = {}
    final: dict[int, list[str]] = {}
    for i, (_, _, slides) in enumerate(CASES):
        deck_slides = [Slide(number=n, text=t) for n, t in enumerate(slides, 1)]
        baseline[i], final[i] = [], []
        for _ in range(args.repeats):
            # One extraction feeds both: its own sector guess is the old behaviour, and the
            # classifier then runs on that same extraction.
            deck = extract_deck(deck_slides, llm, classify=False)
            summary = _summary(deck, deck_slides)
            baseline[i].append(deck.sector.strip().lower())
            final[i].append(resolve_sector(deck.sector, classify_sector(summary, llm), summary))
        print(
            f"{i + 1}/{len(CASES)} {CASES[i][0]:13} baseline={baseline[i]} final={final[i]}",
            flush=True,
        )

    for name, res in (
        ("baseline: sector guessed inside the extraction call", baseline),
        ("classifier: dedicated call with definitions", final),
    ):
        strict, lenient, stable = _score(res)
        print(f"\n{name}")
        print(
            f"  strict {strict:.0%} | benchmark-equivalent {lenient:.0%} | "
            f"identical across {args.repeats} runs {stable:.0%}  ({len(CASES)} decks)"
        )
        print("\n".join(_misses(res)) or "  no misses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
