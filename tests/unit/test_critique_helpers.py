import pytest

from resume_agent.pipelines.critique import _render_critique_md
from resume_agent.prompts.critique import PERSONAS, build


def test_every_persona_has_a_non_empty_system_prompt_and_name():
    assert len(PERSONAS) == 5
    for key, persona in PERSONAS.items():
        assert persona.name
        assert len(persona.system) > 20, key


def test_integrity_auditor_is_the_only_persona_given_the_base_resume():
    assert PERSONAS["integrity_auditor"].needs_base_resume is True
    for key, persona in PERSONAS.items():
        if key != "integrity_auditor":
            assert persona.needs_base_resume is False, key


def test_ats_parser_needs_neither_jd_nor_base_resume():
    assert PERSONAS["ats_parser"].needs_jd is False
    assert PERSONAS["ats_parser"].needs_base_resume is False


def test_build_requires_jd_for_jd_personas():
    with pytest.raises(ValueError, match="requires jd_md"):
        build("recruiter", tailored_md="resume text")


def test_build_requires_base_resume_for_integrity_auditor():
    with pytest.raises(ValueError, match="requires base_originals_only_md"):
        build("integrity_auditor", tailored_md="resume text")


def test_build_includes_jd_but_not_base_resume_for_jd_persona():
    prompt = build("recruiter", tailored_md="RESUME_CONTENT", jd_md="JD_CONTENT")
    assert "RESUME_CONTENT" in prompt
    assert "JD_CONTENT" in prompt
    assert "BASE RESUME" not in prompt


def test_build_includes_base_resume_but_not_jd_for_integrity_auditor():
    prompt = build(
        "integrity_auditor", tailored_md="RESUME_CONTENT", base_originals_only_md="BASE_CONTENT"
    )
    assert "RESUME_CONTENT" in prompt
    assert "BASE_CONTENT" in prompt
    assert "JOB DESCRIPTION" not in prompt


def test_render_critique_md_includes_each_persona_section():
    results = [
        {"persona": key, "ok": True, "verdict": "pass", "findings": []} for key in PERSONAS
    ]
    md = _render_critique_md(results)
    for persona in PERSONAS.values():
        assert f"## {persona.name}" in md


def test_render_critique_md_surfaces_failed_persona_without_crashing():
    results = [{"persona": "ats_parser", "ok": False, "error": "boom"}]
    md = _render_critique_md(results)
    assert "Persona failed: boom" in md


def test_render_critique_md_flags_cross_persona_agreement():
    results = [
        {
            "persona": "ats_parser",
            "ok": True,
            "verdict": "flag",
            "findings": [{"severity": "high", "location": "Skills line", "note": "too dense"}],
        },
        {
            "persona": "recruiter",
            "ok": True,
            "verdict": "flag",
            "findings": [{"severity": "medium", "location": "Skills line", "note": "unfocused"}],
        },
    ]
    md = _render_critique_md(results)
    assert "Cross-Persona Agreement" in md
    assert "Skills line" in md
    assert "ATS Parser Simulation" in md
    assert "Recruiter 6-Second Skim" in md


def test_render_critique_md_omits_agreement_section_when_nothing_overlaps():
    results = [
        {
            "persona": "ats_parser",
            "ok": True,
            "verdict": "flag",
            "findings": [{"severity": "low", "location": "Header", "note": "fine"}],
        },
    ]
    md = _render_critique_md(results)
    assert "Cross-Persona Agreement" not in md
