from resume_agent.prompts import refine_resume, tailor_resume


def test_system_is_the_same_as_tailor_resume():
    # Refining is still "tailor the resume" — same role/constraints, just with
    # feedback folded into the prompt rather than a different persona.
    assert refine_resume.SYSTEM == tailor_resume.SYSTEM


def test_build_includes_the_full_tailor_resume_rule_set():
    prompt = refine_resume.build("RESUME", "JD", [], [])
    # Spot-check a couple of tailor_resume's own rules carry over unmodified,
    # rather than refine_resume silently drifting from them over time.
    assert "never add a skill, tool, or claim" not in prompt  # that line is in SYSTEM, not build()
    assert "Do not add any skill, tool, technology" in prompt  # rule 10
    assert "Never move a bullet" in prompt  # rule 11


def test_build_includes_remaining_gaps_and_suggestions():
    prompt = refine_resume.build(
        "RESUME",
        "JD",
        remaining_gaps=["Kubernetes"],
        improvement_suggestions=[
            {
                "suggestion": "Add 'Spark' to the Skills section.",
                "evidence": "An unused bullet variant mentions Spark.",
                "addresses": "Spark",
            }
        ],
    )
    assert "- Kubernetes" in prompt
    assert "Add 'Spark' to the Skills section." in prompt
    assert "An unused bullet variant mentions Spark." in prompt


def test_build_handles_empty_gaps_and_suggestions():
    prompt = refine_resume.build("RESUME", "JD", [], [])
    assert "(none)" in prompt


def test_build_passes_through_trim_pass_and_always_include_title():
    prompt = refine_resume.build(
        "RESUME",
        "JD",
        [],
        [],
        trim_pass=1,
        always_include_title="Professional Poker Player",
    )
    assert "trim pass 1" in prompt
    assert '"Professional Poker Player"' in prompt
