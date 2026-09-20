"""Quantitative funding benchmark from SEC Form D filings.

Every US company that raises money through a private placement files a Form D, and the SEC
publishes them as quarterly bulk data sets: thousands of real rounds, with the amount sold,
industry group, incorporation age and number of investors, and no model needed to read them.
That makes them the right source for "is this ask normal for its sector?".

What Form D does not have: a description of the business, or a funding stage. So this is a
distribution of raise sizes, not a set of look-alike companies (that is what the S-1 index is
for), and it is stage-agnostic. Amounts are "total amount sold so far", which understates
offerings that are still open.
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
import statistics
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from autopitch.schema import Deck

_INDEX_URL = "https://www.sec.gov/data-research/sec-markets-data/form-d-data-sets"
_BASE = "https://www.sec.gov"
_MIN_INTERVAL = 0.2  # SEC allows 10 requests/second; stay well under
_MIN_PEERS = 20  # fewer same-sector rounds than this and no percentile is reported
_MIN_AMOUNT = 25_000  # below this a filing is a placeholder or a test, not a raise
_MAX_AMOUNT = 5e9

# Industry groups that can plausibly be a venture-backed company. Real estate, pooled funds,
# lodging and the rest are dominated by vehicles that are not startups.
STARTUP_INDUSTRIES = frozenset(
    {
        "Agriculture",
        "Biotechnology",
        "Business Services",
        "Computers",
        "Electric Utilities",
        "Energy Conservation",
        "Environmental Services",
        "Health Insurance",
        "Hospitals and Physicians",
        "Insurance",
        "Manufacturing",
        "Other Banking and Financial Services",
        "Other Energy",
        "Other Health Care",
        "Other Technology",
        "Pharmaceuticals",
        "Restaurants",
        "Retailing",
        "Telecommunications",
    }
)

# Deck sectors are free text from the extraction model. Match on keywords, most specific first.
_SECTOR_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("biotech", "pharma", "therapeutic", "drug", "genom", "life science"),
        ("Biotechnology", "Pharmaceuticals"),
    ),
    (
        ("health", "medic", "clinical", "care", "wellness", "bio"),
        ("Other Health Care", "Hospitals and Physicians", "Health Insurance"),
    ),
    (
        ("fintech", "financ", "payment", "bank", "lending", "insur", "crypto", "wealth"),
        ("Other Banking and Financial Services", "Insurance"),
    ),
    (
        ("climate", "energy", "solar", "battery", "grid", "clean", "sustainab", "carbon", "ev"),
        ("Other Energy", "Energy Conservation", "Environmental Services", "Electric Utilities"),
    ),
    (
        ("telecom", "network", "5g", "wireless"),
        ("Telecommunications",),
    ),
    (
        ("marketplace", "commerce", "consumer", "retail", "food", "restaurant"),
        ("Retailing", "Restaurants"),
    ),
    (
        ("agri", "agtech", "farm"),
        ("Agriculture",),
    ),
    (
        ("hardware", "robot", "manufactur", "industrial", "semiconductor", "device"),
        ("Manufacturing", "Computers"),
    ),
    (
        (
            "saas", "software", "ai", "ml", "machine learning", "data", "cyber", "security",
            "devtool", "cloud", "tech", "platform", "internet", "app", "enterprise",
        ),
        ("Other Technology", "Computers", "Business Services"),
    ),
)  # fmt: skip
_GENERAL = ("Other Technology", "Computers", "Business Services")


def industries_for(sector: str) -> tuple[tuple[str, ...], bool]:
    """Form D industry groups for a deck sector, and whether the sector was recognised."""
    words = re.findall(r"[a-z0-9]+", sector.lower())
    text = " ".join(words)
    for keys, groups in _SECTOR_RULES:
        for key in keys:
            # Short keys must match a whole word ("ai" must not match "retail").
            if (key in words) if len(key) <= 3 else (key in text):
                return groups, True
    return _GENERAL, False


class FormDRound(BaseModel):
    accession: str
    company: str
    cik: str
    industry: str
    amount_sold_usd: float
    offering_usd: float | None = None
    investors: int | None = None
    revenue_range: str | None = None
    filed: str  # ISO date


def _num(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None  # includes "Indefinite" and blanks


def _filed(value: str) -> str | None:
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_quarter(data: bytes) -> list[FormDRound]:
    """Read one quarterly Form D zip and keep the rounds that could be a startup raise."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = {Path(n).name: n for n in z.namelist()}

        def load(name: str) -> list[dict[str, str]]:
            with z.open(names[name]) as f:
                return list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"), delimiter="\t"))

        offerings = {r["ACCESSIONNUMBER"]: r for r in load("OFFERING.tsv")}
        submissions = {r["ACCESSIONNUMBER"]: r for r in load("FORMDSUBMISSION.tsv")}
        issuers = load("ISSUERS.tsv")

    # An amendment restates an earlier filing; keep only the latest of each chain.
    superseded = {
        o["PREVIOUSACCESSIONNUMBER"] for o in offerings.values() if o["ISAMENDMENT"] == "true"
    }
    rounds = []
    for issuer in issuers:
        acc = issuer["ACCESSIONNUMBER"]
        offering, sub = offerings.get(acc), submissions.get(acc)
        if not offering or not sub or acc in superseded or issuer["IS_PRIMARYISSUER_FLAG"] != "YES":
            continue
        if sub["TESTORLIVE"] != "LIVE" or offering["INDUSTRYGROUPTYPE"] not in STARTUP_INDUSTRIES:
            continue
        if offering["INVESTMENTFUNDTYPE"] or offering["ISPOOLEDINVESTMENTFUNDTYPE"] == "true":
            continue
        if issuer["ENTITYTYPE"] not in ("Corporation", "Limited Liability Company"):
            continue
        if issuer["YEAROFINC_TIMESPAN_CHOICE"] != "withinFiveYears":
            continue  # young companies only: this is a startup benchmark
        if offering["ISEQUITYTYPE"] != "true" or offering["ISDEBTTYPE"] == "true":
            continue
        sold, filed = _num(offering["TOTALAMOUNTSOLD"]), _filed(sub["FILING_DATE"])
        if sold is None or filed is None or not _MIN_AMOUNT <= sold <= _MAX_AMOUNT:
            continue
        invested = _num(offering["TOTALNUMBERALREADYINVESTED"])
        revenue = offering["REVENUERANGE"]
        rounds.append(
            FormDRound(
                accession=acc,
                company=issuer["ENTITYNAME"].strip(),
                cik=issuer["CIK"],
                industry=offering["INDUSTRYGROUPTYPE"],
                amount_sold_usd=sold,
                offering_usd=_num(offering["TOTALOFFERINGAMOUNT"]),
                investors=int(invested) if invested is not None else None,
                revenue_range=revenue if revenue and revenue != "Decline to Disclose" else None,
                filed=filed,
            )
        )
    return rounds


def list_quarter_urls(client: httpx.Client) -> dict[str, str]:
    """Map '2025q3' to the download URL by reading the SEC's data-set index page."""
    html = client.get(_INDEX_URL).raise_for_status().text
    found = re.findall(r'href="(/files/[^"]*/form-d-data-sets/(\d{4}q\d)_d\.zip)"', html)
    return {quarter: _BASE + path for path, quarter in found}


def make_client(user_agent: str) -> httpx.Client:
    if "@" not in user_agent:
        raise ValueError(
            "SEC requires a User-Agent with a contact email (AUTOPITCH_SEC_USER_AGENT)."
        )
    return httpx.Client(headers={"User-Agent": user_agent}, timeout=120.0, follow_redirects=True)


def download_quarter(client: httpx.Client, url: str) -> bytes:
    time.sleep(_MIN_INTERVAL)
    return client.get(url).raise_for_status().content


_SCHEMA = """
CREATE TABLE IF NOT EXISTS rounds (
    accession TEXT PRIMARY KEY,
    company TEXT NOT NULL,
    cik TEXT NOT NULL,
    industry TEXT NOT NULL,
    amount_sold_usd REAL NOT NULL,
    offering_usd REAL,
    investors INTEGER,
    revenue_range TEXT,
    filed TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS rounds_industry ON rounds(industry, amount_sold_usd);
"""


class FormDStore:
    def __init__(self, path: str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(_SCHEMA)

    def upsert(self, rounds: list[FormDRound]) -> int:
        rows = [
            (r.accession, r.company, r.cik, r.industry, r.amount_sold_usd, r.offering_usd,
             r.investors, r.revenue_range, r.filed)
            for r in rounds
        ]  # fmt: skip
        with self._lock:
            self._db.executemany("INSERT OR REPLACE INTO rounds VALUES (?,?,?,?,?,?,?,?,?)", rows)
            self._db.commit()
        return len(rows)

    def amounts(self, industries: tuple[str, ...]) -> list[float]:
        marks = ",".join("?" * len(industries))
        with self._lock:
            cur = self._db.execute(
                f"SELECT amount_sold_usd FROM rounds WHERE industry IN ({marks})"
                " ORDER BY amount_sold_usd",
                industries,
            )
            return [row[0] for row in cur]

    def industry_counts(self) -> list[tuple[str, int]]:
        with self._lock:
            cur = self._db.execute(
                "SELECT industry, COUNT(*) FROM rounds GROUP BY industry ORDER BY 2 DESC"
            )
            return [(row[0], row[1]) for row in cur]

    def coverage(self) -> tuple[int, str | None, str | None]:
        with self._lock:
            n, lo, hi = self._db.execute(
                "SELECT COUNT(*), MIN(filed), MAX(filed) FROM rounds"
            ).fetchone()
        return n, lo, hi


class FormDStats(BaseModel):
    """How the deck's raise sits among real, recent private raises in its sector."""

    industries: list[str] = Field(description="Form D industry groups the sector mapped to")
    sector_recognised: bool = True
    peers: int = 0
    p25_usd: float | None = None
    median_usd: float | None = None
    p75_usd: float | None = None
    p90_usd: float | None = None
    ask_percentile: float | None = Field(
        default=None, description="Share of peer raises at or below the deck's ask, 0-100"
    )
    period_start: str | None = None
    period_end: str | None = None
    flags: list[str] = Field(default_factory=list)


def _quantile(values: list[float], q: float) -> float:
    """Linear-interpolated quantile of a sorted list."""
    pos = (len(values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def benchmark_formd(deck: Deck, store: FormDStore) -> FormDStats | None:
    """None when the store is empty; otherwise stats, or a flag when peers are too few."""
    total, start, end = store.coverage()
    if total == 0:
        return None
    industries, recognised = industries_for(deck.sector)
    stats = FormDStats(
        industries=list(industries),
        sector_recognised=recognised,
        period_start=start,
        period_end=end,
    )
    if not recognised:
        stats.flags.append(
            f"Sector '{deck.sector}' was not recognised; compared with general technology raises."
        )
    amounts = store.amounts(industries)
    stats.peers = len(amounts)
    if len(amounts) < _MIN_PEERS:
        stats.flags.append(
            f"Only {len(amounts)} comparable Form D raises are indexed; too few for a distribution."
        )
        return stats

    stats.p25_usd = _quantile(amounts, 0.25)
    stats.median_usd = statistics.median(amounts)
    stats.p75_usd = _quantile(amounts, 0.75)
    stats.p90_usd = _quantile(amounts, 0.90)
    ask = deck.financials.raise_amount_usd
    if not ask:
        stats.flags.append(
            "Deck does not state a raise amount, so it cannot be placed in the range."
        )
        return stats

    at_or_below = sum(1 for a in amounts if a <= ask)
    stats.ask_percentile = round(100 * at_or_below / len(amounts), 1)
    if stats.ask_percentile >= 90:
        stats.flags.append(
            f"Ask of ${ask:,.0f} is larger than {stats.ask_percentile:.0f}% of recent private "
            f"raises in this sector (median ${stats.median_usd:,.0f})."
        )
    elif stats.ask_percentile <= 10:
        stats.flags.append(
            f"Ask of ${ask:,.0f} is smaller than {100 - stats.ask_percentile:.0f}% of recent "
            f"private raises in this sector (median ${stats.median_usd:,.0f}); check runway."
        )
    return stats
