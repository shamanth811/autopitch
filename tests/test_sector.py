import typing

import pytest

from autopitch.llm.fake import FakeLLM
from autopitch.parsing.extract import _summary, extract_deck, resolve_sector
from autopitch.parsing.sector import (
    _KEYWORDS,
    DEFINITIONS,
    SECTORS,
    SectorLabel,
    _Choice,
    classify_sector,
    keyword_sector,
)
from autopitch.retrieval.formd import industries_for
from autopitch.schema import Deck, Slide


def _choice(sector: str) -> _Choice:
    return _Choice(reasoning="sells X to Y", sector=sector)


def test_vocabulary_definitions_keywords_and_type_agree():
    assert set(DEFINITIONS) == set(SECTORS) | {"other"}
    assert set(_KEYWORDS) == set(SECTORS)
    assert set(typing.get_args(SectorLabel)) == set(SECTORS) | {"other"}
    for label in SECTORS:
        assert industries_for(label)[1], f"{label} has no Form D mapping"


def test_classifier_returns_the_models_label_and_sees_every_definition():
    llm = FakeLLM({_Choice: _choice("fintech")})
    assert classify_sector("Company: Payco", llm) == "fintech"
    _, system, prompt = llm.calls[0]
    assert all(name in system for name in DEFINITIONS)
    assert "<deck>" in prompt and "Payco" in prompt  # untrusted text is fenced


def test_the_output_type_cannot_hold_a_label_outside_the_vocabulary():
    with pytest.raises(ValueError):
        _Choice(reasoning="x", sector="space-mining")


def test_classifier_reports_none_when_the_model_fails():
    assert classify_sector("anything", FakeLLM()) is None  # FakeLLM raises LLMError


@pytest.mark.parametrize(
    ("guess", "classified", "text", "expected"),
    [
        ("saas", "healthtech", "", "healthtech"),  # the classifier outranks the extractor
        ("Climate ", "climate", "", "climate"),
        ("saas", "other", "", "saas"),  # "other" defers to a valid guess
        ("unknown", "other", "", "other"),
        ("energy", None, "", "energy"),  # classifier down: the extractor's valid guess
        ("unknown", None, "solar solar battery battery", "energy"),  # then keywords
        ("unknown", None, "nothing useful here", "unknown"),
        ("made-up", None, "", "unknown"),  # an invalid guess is never passed through
    ],
)
def test_resolve_sector(guess, classified, text, expected):
    assert resolve_sector(guess, classified, text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("We build drug candidates; preclinical data and a clinical trial next year.", "biotech"),
        ("Farmers use our soil sensors to time the harvest of each crop.", "agtech"),
        ("one mention of a solar panel", None),  # a single hit is too weak to call
        ("solar solar marketplace marketplace", None),  # a tie is not a call
        ("", None),
    ],
)
def test_keyword_fallback_only_answers_when_it_is_confident(text, expected):
    assert keyword_sector(text) == expected


def _slides():
    return [Slide(number=1, text="Acme\nDemand-response software"), Slide(number=2, text="More")]


def test_extract_deck_lets_the_classifier_decide_the_sector(sample_deck):
    sample_deck.sector = "unknown"
    llm = FakeLLM({Deck: sample_deck, _Choice: _choice("climate")})
    assert extract_deck(_slides(), llm, classify=True).sector == "climate"
    assert [c[0] for c in llm.calls] == ["Deck", "_Choice"]


def test_extract_deck_survives_a_classifier_failure(sample_deck):
    sample_deck.sector = "energy"
    assert extract_deck(_slides(), FakeLLM({Deck: sample_deck}), classify=True).sector == "energy"
    # An invalid guess is never passed through; keywords take over. The sample deck describes
    # "demand-response software", which is a climate signal.
    sample_deck.sector = "who knows"
    assert extract_deck(_slides(), FakeLLM({Deck: sample_deck}), classify=True).sector == "climate"


def test_the_classifier_call_is_off_by_default(sample_deck):
    sample_deck.sector = "saas"
    llm = FakeLLM({Deck: sample_deck, _Choice: _choice("climate")})
    assert extract_deck(_slides(), llm).sector == "saas"
    assert [c[0] for c in llm.calls] == ["Deck"]  # one call, no classifier


def test_the_guess_is_validated_even_without_the_classifier(sample_deck):
    sample_deck.sector = "Energy "
    assert extract_deck(_slides(), FakeLLM({Deck: sample_deck})).sector == "energy"
    sample_deck.sector = "who knows"  # not in the vocabulary: keywords take over
    assert extract_deck(_slides(), FakeLLM({Deck: sample_deck})).sector == "climate"


def test_the_classifier_sees_a_short_summary_not_the_whole_deck(sample_deck):
    long_slides = [Slide(number=i, text="x" * 5000) for i in range(1, 6)]
    summary = _summary(sample_deck, long_slides)
    assert sample_deck.company in summary and sample_deck.one_liner in summary
    assert len(summary) < 2500


def test_null_fields_from_the_extractor_fall_back_to_defaults():
    deck = Deck.model_validate(
        {
            "company": "Acme",
            "problem": {"statement": None, "evidence": None, "target_customer": None},
            "market": {"tam_usd": None, "sources": None},
            "team": {"founders": None, "headcount": None},
            "one_liner": None,
        }
    )
    assert deck.problem.statement == "" and deck.problem.evidence == []
    assert deck.market.sources == [] and deck.team.founders == []
    assert deck.one_liner is None


def test_a_missing_required_field_is_still_an_error():
    with pytest.raises(ValueError):
        Deck.model_validate({"company": None})
