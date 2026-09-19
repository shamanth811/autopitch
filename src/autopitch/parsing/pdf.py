"""Turn an uploaded PDF into per-slide text."""

from __future__ import annotations

import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from autopitch.schema import Slide


class DeckParseError(ValueError):
    pass


def read_slides(data: bytes) -> list[Slide]:
    """Extract text page by page. Each PDF page is treated as one slide."""
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except (PdfReadError, ValueError) as exc:
        raise DeckParseError(f"Could not read PDF: {exc}") from exc

    slides = [Slide(number=i, text=text) for i, text in enumerate(pages, start=1) if text]
    if not slides:
        raise DeckParseError(
            "No extractable text found. The deck is probably image-only; run OCR first."
        )
    return slides


def slides_to_prompt(slides: list[Slide]) -> str:
    return "\n\n".join(f"--- Slide {s.number} ---\n{s.text}" for s in slides)
