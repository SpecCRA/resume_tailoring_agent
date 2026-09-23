"""Eval for the Hiring Manager Technical Depth persona (prompts/critique.py).

Checks both recall (does it catch a planted vague/buzzword bullet) and
precision (does it leave the adjacent quantified bullet alone) in one pass,
since a persona that flags everything is as useless as one that flags nothing.
"""

import pytest

from resume_agent.prompts.critique import PERSONAS, build
from resume_agent.tools.llm import call_llm_json

from .config import EVAL_MODELS
from .fixtures import JOB_DESCRIPTION, VAGUE_BULLET_TAILORED_RESUME

PERSONA = PERSONAS["hiring_manager"]


@pytest.mark.parametrize("model", EVAL_MODELS)
def test_hiring_manager_flags_the_vague_bullet_and_only_the_vague_bullet(real_client, model):
    prompt = build(
        "hiring_manager", tailored_md=VAGUE_BULLET_TAILORED_RESUME, jd_md=JOB_DESCRIPTION
    )
    result = call_llm_json(
        real_client, system=PERSONA.system, prompt=prompt, max_tokens=1024, model=model
    )

    assert result["verdict"] == "flag", f"missed the planted vague bullet ({model})"
    locations = " ".join(f["location"].lower() for f in result["findings"])
    assert "process" in locations or "stakeholder" in locations or "improve" in locations, (
        f"didn't identify the vague bullet by location ({model}): {result['findings']}"
    )
    assert "spark" not in locations and "45 minutes" not in locations, (
        f"false positive on the quantified bullet ({model}): {result['findings']}"
    )
