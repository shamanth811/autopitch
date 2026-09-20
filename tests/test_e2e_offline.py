"""Runs the real sample PDF from disk through parsing and the full graph.

Models are stubbed, so this checks wiring and data flow, not model quality: that text read
from the actual file reaches the extraction prompt, that each scorer receives only its own
section, and that the final report is assembled and renders.
"""

from pathlib import Path

import pytest

from autopitch.graph import build_graph
from autopitch.llm.fake import FakeLLM
from autopitch.objections import _Objections
from autopitch.parsing import read_slides
from autopitch.report import build_report, render_markdown
from autopitch.schema import CriterionScore, Deck, Section
from autopitch.scoring import CRITERIA
from autopitch.scoring.nodes import _SectionJudgement

SAMPLE = Path(__file__).parent.parent / "examples" / "acme_grid_deck.pdf"


@pytest.mark.skipif(not SAMPLE.exists(), reason="run examples/make_sample_deck.py first")
def test_sample_pdf_flows_through_full_graph(sample_deck):
    slides = read_slides(SAMPLE.read_bytes())
    assert len(slides) == 7

    def judge(system, prompt):
        section = next(s for s in Section if f"Section under review: {s.value}" in prompt)
        return _SectionJudgement(
            criteria=[
                CriterionScore(criterion=n, score=6, reasoning="r") for n in CRITERIA[section]
            ],
            summary="s",
        )

    extraction = FakeLLM({Deck: sample_deck, _Objections: _Objections(objections=[])})
    scoring = FakeLLM({_SectionJudgement: judge})
    result = build_graph(extraction, scoring).invoke({"slides": slides})

    # Text from the real file reached the extraction prompt.
    extraction_prompt = extraction.calls[0][2]
    assert "$420,000" in extraction_prompt and "--- Slide 7 ---" in extraction_prompt

    # Six scorers ran, once each.
    assert sorted(c[0] for c in scoring.calls) == ["_SectionJudgement"] * 6

    report = build_report(result)
    assert report.composite.score == pytest.approx(6.0)
    assert "# Pitch analysis: Acme Grid" in render_markdown(report)
