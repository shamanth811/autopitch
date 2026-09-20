"""LangGraph pipeline.

    START -> parse -> [problem | market | traction | team | moat | financials]
          -> aggregate -> benchmark -> objections -> END

The six scorers share no state with each other. Each writes its own SectionScore, and a
list-append reducer merges them at the join. The benchmark node does nothing unless a
retrieval backend (S-1 index, Form D store or both) is supplied.
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
from autopitch.retrieval.formd import FormDStore, benchmark_formd
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
    formd_store: FormDStore | None = None,
    classify_sector: bool = False,
):
    def parse(state: PitchState) -> PitchState:
        if "deck" in state:  # caller already has a structured deck
            return {}
        return {"deck": extract_deck(state["slides"], extraction_llm, classify_sector)}

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
        deck = state["deck"]
        similar = (
            benchmark_deck(deck, embedder, store)
            if embedder is not None and store is not None
            else None
        )
        stats = benchmark_formd(deck, formd_store) if formd_store is not None else None
        if similar is None and stats is None:
            return {}
        result = similar or Benchmark()
        result.formd = stats
        return {"benchmark": result}

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
