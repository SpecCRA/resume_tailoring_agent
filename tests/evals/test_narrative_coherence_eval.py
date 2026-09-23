"""Eval for the Narrative Coherence persona (prompts/critique.py).

This is the most subjective of the five personas — there's no clean automated
ground truth for "is this a good story" — so it's held to a lower bar than the
others: not a coherence-score assertion, just a check that it doesn't invent a
complaint about content it has no way of knowing existed (see the docstring on
NARRATIVE_RESUME_WITH_VALID_OMISSION in fixtures.py for what's actually being
tested here).
"""

import pytest

from resume_agent.prompts.critique import PERSONAS, build
from resume_agent.tools.llm import call_llm_json

from .config import EVAL_MODELS
from .fixtures import JOB_DESCRIPTION, NARRATIVE_RESUME_WITH_VALID_OMISSION

PERSONA = PERSONAS["narrative_coherence"]


@pytest.mark.parametrize("model", EVAL_MODELS)
def test_narrative_coherence_does_not_invent_a_missing_content_complaint(real_client, model):
    prompt = build(
        "narrative_coherence",
        tailored_md=NARRATIVE_RESUME_WITH_VALID_OMISSION,
        jd_md=JOB_DESCRIPTION,
    )
    result = call_llm_json(
        real_client, system=PERSONA.system, prompt=prompt, max_tokens=1024, model=model
    )
    notes = " ".join(f["note"].lower() for f in result["findings"])
    assert "missing" not in notes and "should include" not in notes, (
        f"invented a complaint about content it can't see ({model}): {result['findings']}"
    )
