"""LLM-backed extraction of slide text into the typed `Deck` schema."""

from __future__ import annotations

from autopitch.llm import LLMClient
from autopitch.parsing.pdf import read_slides, slides_to_prompt
from autopitch.safety import notice, wrap_untrusted
from autopitch.schema import Deck, Slide

# The benchmark maps these labels to SEC industry groups (retrieval/formd.py); a test keeps
# the two lists in step.
SECTORS = (
    "saas", "ai", "devtools", "cybersecurity", "fintech", "healthtech", "biotech", "climate",
    "energy", "marketplace", "consumer", "hardware", "telecom", "agtech",
)  # fmt: skip

_SYSTEM = f"""You extract structured data from startup pitch decks.
{notice("deck")}
Rules:
- Use only facts stated in the deck. If a field is not stated, leave it null or empty.
- Never estimate or infer numbers. Copy figures as stated and convert to plain USD
  (e.g. "$2.5M" -> 2500000). Percentages are numbers, so "12%" -> 12.
- `sector` is the one field you classify rather than copy: choose the single best label for
  what the company sells, from: {", ".join(SECTORS)}. The deck rarely names its sector, so infer
  it from the product description. Use "unknown" only if the business is genuinely unclear.
- `stage` is one of: pre-seed, seed, series-a, series-b, later.
"""

# Slide text beyond this is cut so a 100-page deck cannot blow the context window.
_MAX_PROMPT_CHARS = 60_000


def extract_deck(slides: list[Slide], llm: LLMClient) -> Deck:
    body = slides_to_prompt(slides)[:_MAX_PROMPT_CHARS]
    prompt = f"Extract the deck below.\n\n{wrap_untrusted('deck', body)}"
    return llm.generate_structured(_SYSTEM, prompt, Deck)


def parse_pdf(data: bytes, llm: LLMClient) -> Deck:
    return extract_deck(read_slides(data), llm)
