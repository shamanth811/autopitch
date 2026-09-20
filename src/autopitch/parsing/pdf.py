"""Turn an uploaded PDF into per-slide text."""

from __future__ import annotations

import io
import logging

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from autopitch.parsing.ocr import OcrClient, OcrError
from autopitch.schema import Slide

log = logging.getLogger(__name__)


class DeckParseError(ValueError):
    pass


class OcrUnavailableError(DeckParseError):
    """The deck needs OCR but the OCR service could not be used (outage or over its limits)."""


def _pdf_of_pages(reader: PdfReader, indices: list[int]) -> bytes:
    """A new PDF holding only the given pages, so OCR is sent just what it has to read."""
    writer = PdfWriter()
    for i in indices:
        writer.add_page(reader.pages[i])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def read_slides(
    data: bytes, max_pages: int | None = None, ocr: OcrClient | None = None
) -> list[Slide]:
    """Extract text page by page. Each PDF page is treated as one slide.

    `max_pages` is checked before any text extraction so an oversized upload is rejected
    cheaply. Pages with no selectable text (scans, exported images) go to `ocr` when one is
    given; pages that already have text are never sent anywhere. If OCR fails, the deck is
    still analysed from its text pages when it has any, and rejected when it has none.
    """
    try:
        reader = PdfReader(io.BytesIO(data))
        if max_pages is not None and len(reader.pages) > max_pages:
            raise DeckParseError(f"Deck has {len(reader.pages)} pages; the limit is {max_pages}.")
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
        blank = [i for i, text in enumerate(pages) if not text]
        blank_pdf = _pdf_of_pages(reader, blank) if blank and ocr is not None else None
    except (PdfReadError, ValueError) as exc:
        raise DeckParseError(f"Could not read PDF: {exc}") from exc

    if blank_pdf is not None:
        try:
            for i, markdown in zip(blank, ocr.ocr_pdf(blank_pdf), strict=False):
                pages[i] = markdown.strip()
        except OcrError as exc:
            if not any(pages):
                raise OcrUnavailableError(str(exc)) from exc
            log.warning(
                "OCR failed for %d image-only page(s); continuing without: %s", len(blank), exc
            )

    slides = [Slide(number=i, text=text) for i, text in enumerate(pages, start=1) if text]
    if not slides:
        raise DeckParseError(
            "No extractable text found. The deck is probably image-only; run OCR first."
        )
    return slides


def slides_to_prompt(slides: list[Slide]) -> str:
    return "\n\n".join(f"--- Slide {s.number} ---\n{s.text}" for s in slides)
