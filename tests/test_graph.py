import pytest

from autopitch.graph import build_graph
from autopitch.llm.fake import FakeLLM
from autopitch.objections import _Objections
from autopitch.schema import CriterionScore, Deck, Section, SectionScore, Slide
from autopitch.scoring import CRITERIA
from autopitch.scoring.aggregate import compose
from autopitch.scoring.nodes import _SectionJudgement


def _section_score(section: Section, score: float) -> SectionScore:
    return SectionScore(
        section=section,
        score=score,
        criteria=[
            CriterionScore(criterion=n, score=score, reasoning=f"{n} reasoning")
            for n in CRITERIA[section]
        ],
    )


def test_composite_is_weighted_mean():
    scores = [_section_score(sec, 10.0 if sec == Section.TEAM else 0.0) for sec in Section]
    result = compose(scores, "pre-seed")
    assert result.score == pytest.approx(3.5)  # pre-seed team weight is 0.35
    assert result.contributions[Section.TEAM] == pytest.approx(3.5)


def test_unscorable_section_is_excluded_and_weights_renormalised():
    scores = [_section_score(sec, 8.0) for sec in Section if sec != Section.MOAT]
    scores.append(SectionScore(section=Section.MOAT, score=0.0, criteria=[]))
    result = compose(scores, "seed")
    assert result.excluded == [Section.MOAT]
    assert result.score == pytest.approx(8.0)  # not dragged down by the failed section
    assert sum(result.weights.values()) == pytest.approx(1.0)


def test_trace_has_one_line_per_scored_criterion():
    scores = [_section_score(sec, 5.0) for sec in Section]
    result = compose(scores, "seed")
    assert len(result.trace) == sum(len(c) for c in CRITERIA.values())
    assert sum(t.effective_weight * 1 for t in result.trace) == pytest.approx(1.0, abs=0.01)


def test_graph_runs_all_six_scorers_and_composes(sample_deck):
    def judge(system: str, prompt: str) -> _SectionJudgement:
        section = next(s for s in Section if f"Section under review: {s.value}" in prompt)
        return _SectionJudgement(
            criteria=[
                CriterionScore(criterion=n, score=7, reasoning="ok") for n in CRITERIA[section]
            ],
            summary="solid",
        )

    extraction = FakeLLM({Deck: sample_deck, _Objections: _Objections(objections=[])})
    graph = build_graph(extraction, FakeLLM({_SectionJudgement: judge}))
    out = graph.invoke({"slides": [Slide(number=1, text="Acme Grid")]})

    assert {s.section for s in out["scores"]} == set(Section)
    assert out["composite"].score == pytest.approx(7.0)
    assert out["deck"].company == "Acme Grid"
