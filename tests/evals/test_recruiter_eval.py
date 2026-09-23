"""Eval for the Recruiter 6-Second Skim persona (prompts/critique.py).

This persona's whole reason for existing (distinct from Hiring Manager) is
being ORDER-sensitive — an A/B test on bullet order is the direct check of
whether it's actually doing that, versus just re-deriving relevance.
"""

import pytest

from resume_agent.prompts.critique import PERSONAS, build
from resume_agent.tools.llm import call_llm_json

from .config import EVAL_MODELS
from .fixtures import JOB_DESCRIPTION, RECRUITER_STRONG_BULLET_FIRST, RECRUITER_STRONG_BULLET_LAST

PERSONA = PERSONAS["recruiter"]


@pytest.mark.parametrize("model", EVAL_MODELS)
def test_recruiter_is_sensitive_to_whether_the_strongest_bullet_leads(real_client, model):
    def _run(tailored_md):
        prompt = build("recruiter", tailored_md=tailored_md, jd_md=JOB_DESCRIPTION)
        return call_llm_json(
            real_client, system=PERSONA.system, prompt=prompt, max_tokens=1024, model=model
        )

    buried = _run(RECRUITER_STRONG_BULLET_LAST)
    leading = _run(RECRUITER_STRONG_BULLET_FIRST)

    assert buried["verdict"] == "flag", f"missed the buried strongest bullet ({model})"
    assert leading["verdict"] == "pass", (
        f"false positive when the strongest bullet already leads ({model}): {leading['findings']}"
    )
