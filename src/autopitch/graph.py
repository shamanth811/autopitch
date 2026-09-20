"""LangGraph pipeline.

    START -> parse -> [problem | market | traction | team | moat | financials]
          -> aggregate -> benchmark -> objections -> END

The six scorers share no state with each other. Each writes its own SectionScore, and a
list-append reducer merges them at the join. The benchmark node is only added when a
retrieval backend is supplied.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from autopitch.llm import LLMClient
from autopitch.objections import Objection, generate_objections, weak_sections
from autopitch.parsing import extract_deck
from autopitch.retrieval import Embedder, VectorStore
from autopitch.retrieval.benchmark import Benchmark, benchmark_deck
from autopitch.schema import Composite, Deck, Section, SectionScore, Slide
from autopitch.scoring import score_section
from autopitch.scoring.aggregate import compose


class PitchState(TypedDict, total=False):
    slides: list[Slide]
    deck: Deck
    scores: Annotated[list[SectionScore], operator.add]
    composite: Composite
    benchmark: Benchmark
    weak_sections: list[Section]
    objections: list[Objection]


def build_graph(
    extraction_llm: LLMClient,
    scoring_llm: LLMClient,
    embedder: Embedder | None = None,
    store: VectorStore | None = None,
):
    def parse(state: PitchState) -> PitchState:
        if "deck" in state:  # caller already has a structured deck
            return {}
        return {"deck": extract_deck(state["slides"], extraction_llm)}

    def make_scorer(section: Section):
        def scorer(state: PitchState) -> PitchState:
            return {"scores": [score_section(state["deck"], section, scoring_llm)]}

        scorer.__name__ = f"score_{section.value}"
        return scorer

    def aggregate(state: PitchState) -> PitchState:
        return {
            "composite": compose(state["scores"], state["deck"].stage),
            "weak_sections": weak_sections(state["scores"]),
        }

    def benchmark(state: PitchState) -> PitchState:
        if embedder is None or store is None:
            return {}
        return {"benchmark": benchmark_deck(state["deck"], embedder, store)}

    def objections(state: PitchState) -> PitchState:
        return {
            "objections": generate_objections(
                state["deck"], state["scores"], state.get("benchmark"), extraction_llm
            )
        }

    graph = StateGraph(PitchState)
    graph.add_node("parse", parse)
    graph.add_node("aggregate", aggregate)
    graph.add_node("benchmark", benchmark)
    graph.add_node("objections", objections)
    graph.add_edge(START, "parse")

    scorer_nodes = []
    for section in Section:
        name = f"score_{section.value}"
        graph.add_node(name, make_scorer(section))
        graph.add_edge("parse", name)
        scorer_nodes.append(name)

    graph.add_edge(scorer_nodes, "aggregate")  # join: wait for all six
    graph.add_edge("aggregate", "benchmark")
    graph.add_edge("benchmark", "objections")
    graph.add_edge("objections", END)
    return graph.compile()
