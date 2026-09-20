import pytest

from autopitch.llm.fake import FakeLLM
from autopitch.schema import CriterionScore, Section
from autopitch.scoring import CRITERIA, score_section, weights_for
from autopitch.scoring.nodes import _SectionJudgement


def _judgement(section: Section, score: float, skip: str | None = None):
    return _SectionJudgement(
        criteria=[
            CriterionScore(criterion=name, score=score, reasoning="because")
            for name in CRITERIA[section]
            if name != skip
        ],
        summary="fine",
    )


def test_section_score_is_mean_of_criteria_not_model_supplied(sample_deck):
    llm = FakeLLM({_SectionJudgement: _judgement(Section.TRACTION, 6)})
    result = score_section(sample_deck, Section.TRACTION, llm)
    assert result.score == 6
    assert [c.criterion for c in result.criteria] == list(CRITERIA[Section.TRACTION])


def test_unknown_criteria_are_dropped_and_missing_ones_flagged(sample_deck):
    judgement = _judgement(Section.TEAM, 8, skip="completeness")
    judgement.criteria.append(CriterionScore(criterion="vibes", score=10, reasoning="x"))
    result = score_section(sample_deck, Section.TEAM, FakeLLM({_SectionJudgement: judgement}))
    assert result.score == 8
    assert all(c.criterion != "vibes" for c in result.criteria)
    assert any("completeness" in m for m in result.missing_data)


def test_prompt_contains_only_the_target_section(sample_deck):
    llm = FakeLLM({_SectionJudgement: _judgement(Section.MARKET, 5)})
    score_section(sample_deck, Section.MARKET, llm)
    prompt = llm.calls[0][2]
    assert "tam_usd" in prompt
    assert "arr_usd" not in prompt  # traction data must not leak into the market scorer


@pytest.mark.parametrize("stage", ["pre-seed", "seed", "series-a", None, "unheard-of"])
def test_stage_weights_sum_to_one(stage):
    assert sum(weights_for(stage).values()) == pytest.approx(1.0)
