from resume_agent.prompts import tailor_resume


def test_build_omits_always_include_rule_when_not_configured():
    prompt = tailor_resume.build("RESUME", "JD")
    assert "Always include the Experience entry" not in prompt


def test_build_adds_always_include_rule_with_the_configured_title():
    prompt = tailor_resume.build(
        "RESUME", "JD", always_include_title="Professional Poker Player"
    )
    assert '"Professional Poker Player"' in prompt
    assert "Always include the Experience entry titled exactly" in prompt
    assert "never omit it" in prompt
    assert "exactly one bullet" in prompt


def test_build_always_include_rule_appears_on_every_trim_pass():
    for trim_pass in range(3):
        prompt = tailor_resume.build(
            "RESUME", "JD", trim_pass=trim_pass, always_include_title="Professional Poker Player"
        )
        assert '"Professional Poker Player"' in prompt, trim_pass
