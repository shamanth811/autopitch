"""Generate examples/acme_grid_deck.pdf, a fictional seed-stage deck for trying the pipeline.

Acme Grid is invented. Every figure in the deck is made up for demonstration.
"""

from pathlib import Path

from autopitch.testing import make_pdf

SLIDES = [
    "Acme Grid\nDemand-response software for commercial buildings\nSeed round | Raising $3,000,000",
    "The problem\n"
    "Commercial buildings waste roughly 30% of their energy at peak load.\n"
    "Facility managers have no automated way to shed load without hurting tenants.\n"
    "We interviewed 12 facility managers across 9 property portfolios.",
    "Market\n"
    "TAM: $8.0B US commercial demand-response software and services.\n"
    "SAM: $1.2B buildings above 50,000 sq ft in deregulated power markets.\n"
    "SOM: $60M, built bottom-up from 4,000 target buildings at $15,000 per year.",
    "Traction\n"
    "ARR: $420,000 across 14 paying customers.\n"
    "Monthly revenue growth: 9% over the last 6 months.\n"
    "Net revenue retention: 112%. No customer has churned.",
    "Team\n"
    "A. Rao, CEO: 6 years at Tesla Energy on grid services products.\n"
    "M. Iyer, CTO: built load-forecasting models at a regional utility.\n"
    "Team of 7: 4 engineers, 1 data scientist, 1 sales, 1 operations.",
    "Competition and moat\n"
    "Competitors: Enel X, CPower, and in-house building-automation vendors.\n"
    "Our advantage: a proprietary load-forecast model trained on 18 months of meter data.\n"
    "Integrations with 3 building-management systems raise switching costs.",
    "Financials and ask\n"
    "Raising $3.0M seed. Gross margin 68%. Monthly burn $110,000. Runway today: 14 months.\n"
    "Use of funds: 55% engineering, 30% sales hires, 15% pilots in two new power markets.",
]

if __name__ == "__main__":
    out = Path(__file__).with_name("acme_grid_deck.pdf")
    out.write_bytes(make_pdf(SLIDES))
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(SLIDES)} slides)")
