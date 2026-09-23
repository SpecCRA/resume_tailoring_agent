"""Eval for the ATS Parser Simulation persona (prompts/critique.py).

This persona should behave close to deterministic — it's simulating rule-based
software, not exercising judgment — so both a false-positive baseline and a
recall check on planted hazards are meaningful signals of prompt quality.
"""

import pytest

from resume_agent.prompts.critique import PERSONAS, build
from resume_agent.tools.llm import call_llm_json

from .config import EVAL_MODELS
from .fixtures import ATS_HAZARD_TAILORED_RESUME, CLEAN_TAILORED_RESUME

PERSONA = PERSONAS["ats_parser"]


@pytest.mark.parametrize("model", EVAL_MODELS)
def test_ats_parser_has_no_high_severity_findings_on_clean_resume(real_client, model):
    prompt = build("ats_parser", tailored_md=CLEAN_TAILORED_RESUME)
    result = call_llm_json(
        real_client, system=PERSONA.system, prompt=prompt, max_tokens=1024, model=model
    )
    high_severity = [f for f in result["findings"] if f["severity"] == "high"]
    assert not high_severity, f"false positive(s) on a clean resume ({model}): {high_severity}"


@pytest.mark.parametrize("model", EVAL_MODELS)
def test_ats_parser_catches_planted_structural_hazards(real_client, model):
    prompt = build("ats_parser", tailored_md=ATS_HAZARD_TAILORED_RESUME)
    result = call_llm_json(
        real_client, system=PERSONA.system, prompt=prompt, max_tokens=1024, model=model
    )
    assert result["verdict"] == "flag", f"missed planted structural hazards entirely ({model})"
    assert result["findings"], f"flagged but returned no findings ({model})"
