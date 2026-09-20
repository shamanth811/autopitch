"""LLM-backed extraction of slide text into the typed `Deck` schema."""

from __future__ import annotations

from autopitch.llm import LLMClient
from autopitch.parsing.pdf import read_slides, slides_to_prompt
from autopitch.parsing.sector import SECTORS, classify_sector, keyword_sector
from autopitch.safety import notice, wrap_untrusted
from autopitch.schema import Deck, Slide

_SYSTEM = f"""You extract structured data from startup pitch decks.
{notice("deck")}
Rules:
- Use only facts stated in the deck. If a field is not stated, leave it null or empty.
- Never estimate or infer numbers. Copy figures as stated and convert to plain USD
  (e.g. "$2.5M" -> 2500000). Percentages are numbers, so "12%" -> 12.
- `sector` is your best single guess from: {", ".join(SECTORS)}. The deck rarely names its
  sector, so infer it from what the company sells. A separate step makes the final call.
- `stage` is one of: pre-seed, seed, series-a, series-b, later.
"""

# Slide text beyond this is cut so a 100-page deck cannot blow the context window.
_MAX_PROMPT_CHARS = 60_000


def _summary(deck: Deck, slides: list[Slide]) -> str:
    """What the classifier sees: the deck's own description of the business, kept short."""
    lead = "\n".join(s.text for s in slides[:2])[:1200]
    parts = [
        f"Company: {deck.company}",
        f"One-liner: {deck.one_liner or 'n/a'}",
        f"Problem: {deck.problem.statement or 'n/a'}",
        f"Customer: {deck.problem.target_customer or 'n/a'}",
        f"Competitors: {', '.join(deck.moat.competitors) or 'n/a'}",
        f"Opening slides:\n{lead}",
    ]
    return "\n".join(parts)


def resolve_sector(guess: str, classified: str | None, text: str) -> str:
    """Combine the extractor's guess, the classifier's answer and the keyword fallback."""
    guess = guess.strip().lower()
    if classified in SECTORS:
        return classified
    if classified == "other":
        return guess if guess in SECTORS else "other"
    # The classifier did not answer: use the extractor's guess, then keywords.
    if guess in SECTORS:
        return guess
    return keyword_sector(text) or "unknown"


def extract_deck(slides: list[Slide], llm: LLMClient, classify: bool = False) -> Deck:
    body = slides_to_prompt(slides)[:_MAX_PROMPT_CHARS]
    prompt = f"Extract the deck below.\n\n{wrap_untrusted('deck', body)}"
    deck = llm.generate_structured(_SYSTEM, prompt, Deck)
    # Always validate the guess against the vocabulary (falling back to keywords); the second,
    # dedicated model call is opt-in because it cost tokens without a measured gain.
    summary = _summary(deck, slides)
    classified = classify_sector(summary, llm) if classify else None
    deck.sector = resolve_sector(deck.sector, classified, summary)
    return deck


def parse_pdf(data: bytes, llm: LLMClient) -> Deck:
    return extract_deck(read_slides(data), llm)
