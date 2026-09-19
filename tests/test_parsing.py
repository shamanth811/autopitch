import pytest

from autopitch.llm.fake import FakeLLM
from autopitch.parsing import DeckParseError, parse_pdf, read_slides
from autopitch.schema import Deck
from tests.conftest import make_pdf


def test_read_slides_returns_one_slide_per_page():
    slides = read_slides(make_pdf(["Problem slide", "Market slide"]))
    assert [s.number for s in slides] == [1, 2]
    assert "Problem" in slides[0].text


def test_read_slides_rejects_garbage():
    with pytest.raises(DeckParseError):
        read_slides(b"this is not a pdf")


def test_read_slides_rejects_image_only_deck():
    with pytest.raises(DeckParseError, match="OCR"):
        read_slides(make_pdf([""]))


def test_parse_pdf_sends_slide_text_to_llm(sample_deck):
    llm = FakeLLM({Deck: sample_deck})
    deck = parse_pdf(make_pdf(["Acme Grid seed deck"]), llm)
    assert deck.company == "Acme Grid"
    schema_name, _, prompt = llm.calls[0]
    assert schema_name == "Deck"
    assert "Slide 1" in prompt and "Acme Grid" in prompt
