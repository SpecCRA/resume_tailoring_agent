"""Eval for the Integrity Auditor persona (prompts/critique.py) — the one
persona whose failures are actually costly (a missed fabrication is a lie on
someone's resume), so this holds a stricter bar than the other four: any miss
on the recall test should be treated as a blocking regression, not noise.
"""

import pytest

from resume_agent.prompts.critique import PERSONAS, build
from resume_agent.tools.llm import call_llm_json

from .config import EVAL_MODELS
from .fixtures import (
    BASE_RESUME_ORIGINALS_ONLY,
    CLEAN_TAILORED_RESUME,
    FABRICATED_TAILORED_RESUME,
    LEGITIMATE_RELABEL_TAILORED_RESUME,
)

PERSONA = PERSONAS["integrity_auditor"]


def _run(real_client, model, tailored_md):
    prompt = build(
        "integrity_auditor",
        tailored_md=tailored_md,
        base_originals_only_md=BASE_RESUME_ORIGINALS_ONLY,
    )
    return call_llm_json(
        real_client, system=PERSONA.system, prompt=prompt, max_tokens=1024, model=model
    )


@pytest.mark.parametrize("model", EVAL_MODELS)
def test_integrity_auditor_passes_a_clean_resume(real_client, model):
    result = _run(real_client, model, CLEAN_TAILORED_RESUME)
    assert result["verdict"] == "pass", (
        f"false positive on a clean resume ({model}): {result['findings']}"
    )


@pytest.mark.parametrize("model", EVAL_MODELS)
def test_integrity_auditor_catches_every_planted_fabrication(real_client, model):
    result = _run(real_client, model, FABRICATED_TAILORED_RESUME)
    assert result["verdict"] == "flag", f"missed fabrication entirely ({model})"

    combined = " ".join(f["note"] + " " + f["location"] for f in result["findings"]).lower()
    assert "kubernetes" in combined, f"missed the fabricated tool ({model}): {result['findings']}"
    assert any(kw in combined for kw in ["95%", "microservices", "metric", "number", "figure"]), (
        f"missed the fabricated metric ({model}): {result['findings']}"
    )


@pytest.mark.parametrize("model", EVAL_MODELS)
def test_integrity_auditor_does_not_flag_legitimate_jd_relabeling(real_client, model):
    result = _run(real_client, model, LEGITIMATE_RELABEL_TAILORED_RESUME)
    assert result["verdict"] == "pass", (
        f"false positive on legitimate relabeling ({model}): {result['findings']}"
    )
