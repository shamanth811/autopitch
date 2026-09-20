from autopitch.graph import build_graph
from autopitch.llm.fake import FakeLLM
from autopitch.objections import Objection, _Objections, generate_objections, weak_sections
from autopitch.retrieval import FundingPattern, HashEmbedder, InMemoryStore, pattern_text
from autopitch.schema import CriterionScore, Deck, Section, SectionScore, Slide
from autopitch.scoring import CRITERIA
from autopitch.scoring.nodes import _SectionJudgement


def _score(section: Section, value: float, with_criteria: bool = True) -> SectionScore:
    criteria = (
        [CriterionScore(criterion=n, score=value, reasoning="r") for n in CRITERIA[section]]
        if with_criteria
        else []
    )
    return SectionScore(section=section, score=value, criteria=criteria, summary=f"{section} sum")


def test_weak_sections_are_sorted_weakest_first_and_include_unscorable():
    scores = [
        _score(Section.TEAM, 8),
        _score(Section.MARKET, 4.5),
        _score(Section.MOAT, 2),
        _score(Section.FINANCIALS, 0, with_criteria=False),
    ]
    assert weak_sections(scores) == [Section.FINANCIALS, Section.MOAT, Section.MARKET]


def test_objections_prompt_carries_scores_and_are_capped(sample_deck):
    many = _Objections(
        objections=[
            Objection(section=Section.MOAT, question=f"q{i}", basis="b", suggested_response="r")
            for i in range(10)
        ]
    )
    llm = FakeLLM({_Objections: many})
    out = generate_objections(sample_deck, [_score(Section.MOAT, 2)], None, llm)
    assert len(out) == 6
    assert "moat: 2" in llm.calls[0][2]


def test_full_graph_with_retrieval_produces_benchmark_and_objections(sample_deck):
    def judge(system, prompt):
        section = next(s for s in Section if f"Section under review: {s.value}" in prompt)
        return _SectionJudgement(
            criteria=[CriterionScore(criterion=n, score=6, reasoning="ok") for n in CRITERIA[section]],
            summary="fine",
        )

    emb, store = HashEmbedder(), InMemoryStore()
    pats = [
        FundingPattern(id=f"p{i}", company=f"c{i}", sector="climate", stage="seed",
                       round_amount_usd=2e6, year=2020, summary="grid software")
        for i in range(3)
    ]
    store.upsert(pats, emb.embed_documents([pattern_text(p) for p in pats]))
    objection = Objection(section=Section.MOAT, question="Why can't Enel X copy this?",
                          basis="moat 6", suggested_response="Show forecast accuracy data")
    graph = build_graph(
        FakeLLM({Deck: sample_deck, _Objections: _Objections(objections=[objection])}),
        FakeLLM({_SectionJudgement: judge}),
        emb,
        store,
    )
    out = graph.invoke({"slides": [Slide(number=1, text="x")]})
    assert out["benchmark"].median_raise_usd == 2e6
    assert out["objections"][0].question.startswith("Why can't Enel X")
