"""Sector classification.

The benchmark depends on the deck's sector, and sector is the one extracted field that is a
judgement, not a copy. Asking for it inside the large extraction call gave unstable answers
(the same deck came back as "climate", "energy" and "unknown"), so it gets its own small call:
a fixed vocabulary with a definition per label, a reasoning field before the answer, and an
output type that cannot hold anything outside the vocabulary. If the model is unavailable, a
deterministic keyword scorer answers instead.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from autopitch.llm import LLMClient, LLMError
from autopitch.safety import notice, wrap_untrusted

log = logging.getLogger(__name__)

# The benchmark maps these labels to SEC industry groups (retrieval/formd.py); a test keeps
# the two lists in step.
SECTORS = (
    "saas", "ai", "devtools", "cybersecurity", "fintech", "healthtech", "biotech", "climate",
    "energy", "marketplace", "consumer", "hardware", "telecom", "agtech",
)  # fmt: skip

SectorLabel = Literal[
    "saas", "ai", "devtools", "cybersecurity", "fintech", "healthtech", "biotech", "climate",
    "energy", "marketplace", "consumer", "hardware", "telecom", "agtech", "other",
]  # fmt: skip

# What each label means, and how to break ties. Order matters only for readability.
DEFINITIONS = {
    "saas": "business software sold by subscription to companies for a function or a vertical "
    "(HR, sales, logistics, construction, legal, real-estate tools), even if it uses ML inside",
    "ai": "the core product IS a model, agent or AI infrastructure (foundation models, "
    "agents, ML platforms, computer vision or speech products sold as the model itself)",
    "devtools": "products used by software engineers: APIs, infrastructure, observability, "
    "CI/CD, databases, low-code platforms for developers",
    "cybersecurity": "protects systems, identities or data: threat detection, identity, "
    "compliance-automation security, fraud prevention aimed at IT security",
    "fintech": "payments, lending, banking, insurance, wealth, accounting and treasury, crypto; "
    "software whose main value is moving or managing money",
    "healthtech": "healthcare delivery and software: clinics, telehealth, EHR, care "
    "coordination, medical devices and diagnostics tools used in care, digital health",
    "biotech": "drug discovery, therapeutics, genomics, lab science, synthetic biology; "
    "revenue and value depend on clinical or lab results",
    "climate": "cutting emissions or resource use: carbon accounting, efficiency and "
    "demand-response software, recycling, sustainable materials, EV charging software",
    "energy": "producing, storing or delivering energy: solar, wind, batteries, grid hardware, "
    "fuels, oil and gas, utilities",
    "marketplace": "a platform matching buyers and sellers or supply and demand and taking a "
    "fee, including e-commerce marketplaces and gig platforms",
    "consumer": "products and brands sold to individuals: apps, media, gaming, food, "
    "e-commerce brands, subscriptions for consumers",
    "hardware": "physical devices, robotics, semiconductors, manufacturing technology, "
    "drones, industrial equipment",
    "telecom": "connectivity: wireless, satellite, networking equipment or carrier software",
    "agtech": "farming, food production and agricultural inputs or software",
    "other": "none of the above fits, for example real estate, education, legal services or "
    "government; use sparingly",
}

_SYSTEM = f"""You classify a startup into exactly one sector from a fixed list, using its
pitch-deck summary.
{notice("deck")}
Sectors:
{chr(10).join(f"- {name}: {text}" for name, text in DEFINITIONS.items())}

Rules:
- Classify by what the company SELLS and to whom, not by the technology it uses. A logistics
  tool that uses ML is saas, not ai. A hospital scheduling product is healthtech, not saas.
- If two sectors fit, pick the one where the buyer's budget comes from (a bank's budget:
  fintech; a hospital's: healthtech; an engineering team's: devtools).
- `reasoning` is one sentence naming what is sold and to whom. Write it before the answer.
"""


class _Choice(BaseModel):
    reasoning: str = Field(description="One sentence: what the company sells and to whom")
    sector: SectorLabel


def classify_sector(summary: str, llm: LLMClient) -> str | None:
    """A label from SECTORS, "other", or None when the model could not answer."""
    prompt = f"Deck summary:\n{wrap_untrusted('deck', summary)}"
    try:
        return llm.generate_structured(_SYSTEM, prompt, _Choice).sector
    except LLMError as exc:
        log.warning("sector classification failed, using keywords: %s", exc)
        return None


# Fallback only: a deliberately small keyword scorer, used when no model answers.
_KEYWORDS: dict[str, tuple[str, ...]] = {
    "biotech": ("drug", "therapeutic", "clinical trial", "genom", "antibod", "oncolog", "preclinical"),
    "healthtech": ("patient", "clinic", "hospital", "telehealth", "ehr", "physician", "diagnos"),
    "fintech": ("payment", "lending", "bank", "insurance", "wealth", "credit", "invoice", "ledger"),
    "cybersecurity": ("security", "threat", "breach", "phishing", "zero trust", "soc 2", "identity"),
    "devtools": ("developer", "api", "sdk", "open source", "observability", "ci/cd", "deploy"),
    "ai": ("foundation model", "llm", "machine learning model", "agents", "neural", "inference"),
    "climate": ("carbon", "emission", "decarbon", "demand-response", "sustainab", "recycl"),
    "energy": ("solar", "battery", "wind", "grid storage", "oil", "gas", "utility", "energy storage"),
    "marketplace": ("marketplace", "buyers and sellers", "two-sided", "take rate", "gig"),
    "consumer": ("consumers", "shoppers", "gaming", "creators", "d2c", "subscribers"),
    "hardware": ("robot", "sensor", "semiconductor", "device", "manufactur", "drone", "chip"),
    "telecom": ("wireless", "5g", "satellite", "carrier", "spectrum", "broadband"),
    "agtech": ("farm", "crop", "agricultur", "livestock", "soil", "harvest"),
    "saas": ("saas", "subscription software", "workflow", "platform for teams", "b2b software"),
}  # fmt: skip


def keyword_sector(text: str) -> str | None:
    """Best keyword match, or None if nothing scores at least 2 (too weak to call)."""
    low = text.lower()
    scores = {
        label: sum(len(re.findall(re.escape(k), low)) for k in keys)
        for label, keys in _KEYWORDS.items()
    }
    label, best = max(scores.items(), key=lambda kv: kv[1])
    if best < 2:
        return None
    # A tie is not a call: better to say nothing than to pick by dictionary order.
    if sum(1 for v in scores.values() if v == best) > 1:
        return None
    return label
