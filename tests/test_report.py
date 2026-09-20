from autopitch.graph import build_graph
from autopitch.llm.fake import FakeLLM
from autopitch.objections import Objection, _Objections
from autopitch.report import Report, build_report, render_markdown
from autopitch.schema import Composite, CriterionScore, Deck, Section, Slide
from autopitch.scoring import CRITERIA
from autopitch.scoring.nodes import _SectionJudgement


def _run(sample_deck):
    def judge(system, prompt):
        section = next(s for s in Section if f"Section under review: {s.value}" in prompt)
        score = 3 if section == Section.MOAT else 8
        return _SectionJudgement(
            criteria=[
                CriterionScore(criterion=n, score=score, reasoning=f"{n} why")
                for n in CRITERIA[section]
            ],
            summary=f"{section.value} summary",
        )

    obj = Objection(
        section=Section.MOAT,
        question="What stops Enel X?",
        basis="moat 3",
        suggested_response="Forecast accuracy data",
    )
    graph = build_graph(
        FakeLLM({Deck: sample_deck, _Objections: _Objections(objections=[obj])}),
        FakeLLM({_SectionJudgement: judge}),
    )
    return graph.invoke({"slides": [Slide(number=1, text="x")]})


def test_report_orders_sections_and_flags_weak(sample_deck):
    report = build_report(_run(sample_deck))
    assert [s.section for s in report.sections] == list(Section)
    assert report.weak_sections == [Section.MOAT]


def test_markdown_contains_key_sections(sample_deck):
    md = render_markdown(build_report(_run(sample_deck)))
    assert md.startswith("# Pitch analysis: Acme Grid")
    assert "| moat (weak) | 3.0 |" in md
    assert "What stops Enel X?" in md
    assert "not investment advice" in md
    assert "Benchmark" not in md  # no retrieval backend was configured


def test_report_round_trips_through_json(sample_deck):
    report = build_report(_run(sample_deck))
    again = type(report).model_validate_json(report.model_dump_json())
    assert again.composite.score == report.composite.score


def test_markdown_shows_form_d_distribution_and_skips_empty_s1_section(sample_deck):
    from autopitch.retrieval.benchmark import Benchmark
    from autopitch.retrieval.formd import FormDStats

    stats = FormDStats(
        industries=["Other Energy"], peers=185, p25_usd=5e5, median_usd=2.9e6, p75_usd=1.5e7,
        p90_usd=4.4e7, ask_percentile=52.0, period_start="2024-07-01", period_end="2026-06-30",
    )  # fmt: skip
    report = Report(
        deck=sample_deck,
        composite=Composite(score=6.0, weights={}, contributions={}),
        sections=[],
        weak_sections=[],
        benchmark=Benchmark(formd=stats),
    )
    md = render_markdown(report)
    assert "## Raise size against SEC Form D filings" in md
    assert "185 private raises" in md and "52th percentile" in md
    assert "size only" in md
    assert "Similar companies in SEC S-1 filings" not in md
