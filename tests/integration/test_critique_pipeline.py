import json
from unittest.mock import MagicMock, patch

import pytest

from resume_agent.errors import InvalidSlugError, MarkdownFileNotFoundError
from resume_agent.pipelines import setup as setup_pipeline
from resume_agent.pipelines.critique import run_critique
from resume_agent.prompts.critique import PERSONAS


def _fake_message(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


def _write_base_resume(base_path):
    from resume_agent.models.resume import BulletPoint, ExperienceEntry, Resume

    resume = Resume(
        name="Jordan Rivera",
        email="jordan@example.com",
        phone="555-0100",
        linkedin="",
        github="",
        location="Remote",
        summary="Senior engineer.",
        skills=["Python"],
        experience=[
            ExperienceEntry(
                company="Acme Corp",
                title="Senior Engineer",
                dates="2019-2023",
                bullets=[BulletPoint(original="Shipped a thing", variants=["Variant A"])],
            ),
        ],
        education=[],
        projects=[],
    )
    base_path.write_text(setup_pipeline._render_base_md(resume))


def _canned_finding(location: str):
    return {
        "verdict": "flag",
        "findings": [{"severity": "medium", "location": location, "note": "example finding"}],
    }


@pytest.fixture
def critique_env(tmp_path, monkeypatch):
    from resume_agent.config import settings

    base_path = tmp_path / "resume_base.md"
    _write_base_resume(base_path)
    output_dir = tmp_path / "output"
    jobs_dir = tmp_path / "data" / "jobs"
    output_dir.mkdir()
    jobs_dir.mkdir(parents=True)

    (output_dir / "acme-platform-engineer.md").write_text(
        "# Jordan Rivera\n\n## Experience\n- Shipped a thing\n"
    )
    (jobs_dir / "acme-platform-engineer.md").write_text("# Platform Engineer — Acme\n")

    monkeypatch.setattr(settings, "base_resume_path", str(base_path))
    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"))
    monkeypatch.setattr(settings, "output_dir", str(output_dir))
    monkeypatch.setattr(settings, "eval_model", "claude-eval-test-model")
    return output_dir


def test_run_critique_writes_a_section_per_persona(critique_env):
    output_dir = critique_env

    def _fake_create(*, model=None, **kwargs):
        assert model == "claude-eval-test-model"
        return _fake_message(json.dumps({"verdict": "pass", "findings": []}))

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = _fake_create

    with patch("resume_agent.pipelines.critique.anthropic.Anthropic", return_value=fake_client):
        report_path = run_critique("acme-platform-engineer")

    assert report_path == output_dir / "acme-platform-engineer.critique.md"
    content = report_path.read_text()
    for persona in PERSONAS.values():
        assert f"## {persona.name}" in content
    assert fake_client.messages.create.call_count == len(PERSONAS)


def test_run_critique_withholds_jd_from_integrity_auditor_only(critique_env):
    seen_prompts: dict[str, str] = {}

    def _fake_create(*, system=None, messages=None, **kwargs):
        for key, persona in PERSONAS.items():
            if persona.system == system:
                seen_prompts[key] = messages[0]["content"]
        return _fake_message(json.dumps({"verdict": "pass", "findings": []}))

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = _fake_create

    with patch("resume_agent.pipelines.critique.anthropic.Anthropic", return_value=fake_client):
        run_critique("acme-platform-engineer")

    assert "JOB DESCRIPTION" not in seen_prompts["integrity_auditor"]
    assert "BASE RESUME" in seen_prompts["integrity_auditor"]
    for key, persona in PERSONAS.items():
        if persona.needs_jd:
            assert "JOB DESCRIPTION" in seen_prompts[key], key
        else:
            assert "JOB DESCRIPTION" not in seen_prompts[key], key
        if persona.needs_base_resume:
            assert "BASE RESUME" in seen_prompts[key], key
        else:
            assert "BASE RESUME" not in seen_prompts[key], key


def test_run_critique_survives_one_persona_failing(critique_env):
    def _fake_create(*, system=None, **kwargs):
        if system == PERSONAS["ats_parser"].system:
            raise Exception("simulated API failure")
        return _fake_message(json.dumps(_canned_finding("Skills")))

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = _fake_create

    with patch("resume_agent.pipelines.critique.anthropic.Anthropic", return_value=fake_client):
        report_path = run_critique("acme-platform-engineer")

    content = report_path.read_text()
    assert "## ATS Parser Simulation" in content
    for persona in PERSONAS.values():
        assert f"## {persona.name}" in content


def test_run_critique_rejects_missing_tailored_resume(critique_env):
    with pytest.raises(MarkdownFileNotFoundError):
        run_critique("no-such-job")


def test_run_critique_rejects_missing_job_description(critique_env):
    output_dir = critique_env
    (output_dir / "no-jd.md").write_text("# Resume\n")

    with pytest.raises(MarkdownFileNotFoundError):
        run_critique("no-jd")


@pytest.mark.parametrize(
    "bad_slug",
    ["../../etc/passwd", "../secret", "Acme Corp", "acme/../../role", "UPPERCASE"],
)
def test_run_critique_rejects_a_slug_that_isnt_path_safe(critique_env, bad_slug):
    with pytest.raises(InvalidSlugError):
        run_critique(bad_slug)


def test_run_critique_never_touches_the_filesystem_for_an_invalid_slug(critique_env, tmp_path):
    # A successful path-traversal slug would read/write outside output_dir —
    # confirm nothing outside the sandboxed tmp_path tree gets created at all.
    before = set(tmp_path.rglob("*"))
    with pytest.raises(InvalidSlugError):
        run_critique("../../etc/passwd")
    after = set(tmp_path.rglob("*"))
    assert before == after


def test_run_critique_degrades_gracefully_on_a_malformed_persona_response(critique_env):
    def _fake_create(*, system=None, **kwargs):
        if system == PERSONAS["ats_parser"].system:
            # Missing "note", and an out-of-schema severity — a plausible way
            # a response could drift from _SCHEMA_INSTRUCTIONS despite the ask.
            return _fake_message(
                json.dumps(
                    {
                        "verdict": "flag",
                        "findings": [{"severity": "critical", "location": "Header"}],
                    }
                )
            )
        return _fake_message(json.dumps(_canned_finding("Skills")))

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = _fake_create

    with patch("resume_agent.pipelines.critique.anthropic.Anthropic", return_value=fake_client):
        report_path = run_critique("acme-platform-engineer")

    content = report_path.read_text()
    assert "## ATS Parser Simulation" in content
    assert "Persona failed: Response didn't match the expected schema" in content
    # The other four personas' results must still be present, unaffected.
    for key, persona in PERSONAS.items():
        if key != "ats_parser":
            assert f"## {persona.name}" in content
    assert content.count("[medium] Skills: example finding") == len(PERSONAS) - 1
