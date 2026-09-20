"""LangGraph pipeline: parse -> six parallel section scorers -> composite.

    START -> parse -> [problem | market | traction | team | moat | financials] -> aggregate -> END

The six scorers share no state with each other. Each writes its own SectionScore, and a
list-append reducer merges them at the join.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from autopitch.llm import LLMClient
from autopitch.parsing import extract_deck
from autopitch.schema import Composite, Deck, Section, SectionScore, Slide
from autopitch.scoring import score_section
from autopitch.scoring.aggregate import compose


class PitchState(TypedDict, total=False):
    slides: list[Slide]
    deck: Deck
    scores: Annotated[list[SectionScore], operator.add]
    composite: Composite


def build_graph(extraction_llm: LLMClient, scoring_llm: LLMClient):
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
        return {"composite": compose(state["scores"], state["deck"].stage)}

    graph = StateGraph(PitchState)
    graph.add_node("parse", parse)
    graph.add_node("aggregate", aggregate)
    graph.add_edge(START, "parse")

    scorer_nodes = []
    for section in Section:
        name = f"score_{section.value}"
        graph.add_node(name, make_scorer(section))
        graph.add_edge("parse", name)
        scorer_nodes.append(name)

    graph.add_edge(scorer_nodes, "aggregate")  # join: wait for all six
    graph.add_edge("aggregate", END)
    return graph.compile()
