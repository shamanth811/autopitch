"""Independent per-section scorers.

Each scorer sees only its own section (plus company, sector and stage for context), so a
strong team slide cannot inflate a weak market slide. The LLM supplies per-criterion
scores and reasoning; the section score itself is computed here, not by the model.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from autopitch.llm import LLMClient
from autopitch.safety import notice, wrap_untrusted
from autopitch.schema import CriterionScore, Deck, Section, SectionScore
from autopitch.scoring.rubric import CRITERIA

_SYSTEM = f"""You are a seed-stage venture investor scoring one section of a pitch deck.
{notice("section_data")}
Score each listed criterion from 0 to 10 using only the extracted data provided.
- 0-2: absent or actively concerning. 3-4: weak. 5-6: acceptable. 7-8: strong. 9-10: exceptional.
- If the data needed for a criterion is missing, score it low and name what is missing in
  `missing_data`. Do not assume good news the deck did not state.
- `reasoning` must cite specific values or claims from the data, in one or two sentences.
"""


class _SectionJudgement(BaseModel):
    criteria: list[CriterionScore]
    summary: str = Field(description="Two-sentence verdict on this section")
    missing_data: list[str] = Field(default_factory=list)


def _prompt(deck: Deck, section: Section) -> str:
    criteria = "\n".join(f"- {name}: {desc}" for name, desc in CRITERIA[section].items())
    data = getattr(deck, section.value).model_dump_json(indent=2)
    return (
        f"Company: {deck.company}\nSector: {deck.sector}\nStage: {deck.stage or 'unknown'}\n"
        f"One-liner: {deck.one_liner or 'n/a'}\n\n"
        f"Section under review: {section.value}\n\nCriteria:\n{criteria}\n\n"
        f"Extracted section data:\n{wrap_untrusted('section_data', data)}"
    )


def score_section(deck: Deck, section: Section, llm: LLMClient) -> SectionScore:
    judgement = llm.generate_structured(_SYSTEM, _prompt(deck, section), _SectionJudgement)

    expected = set(CRITERIA[section])
    by_name = {c.criterion: c for c in judgement.criteria if c.criterion in expected}
    missing = list(judgement.missing_data)
    for name in expected - by_name.keys():
        missing.append(f"model did not score criterion '{name}'")

    kept = [by_name[name] for name in CRITERIA[section] if name in by_name]
    if not kept:
        return SectionScore(
            section=section, score=0.0, criteria=[], summary=judgement.summary, missing_data=missing
        )
    score = round(sum(c.score for c in kept) / len(kept), 2)
    return SectionScore(
        section=section,
        score=score,
        criteria=kept,
        summary=judgement.summary,
        missing_data=missing,
    )
