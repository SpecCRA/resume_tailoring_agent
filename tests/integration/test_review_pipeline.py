from unittest.mock import MagicMock, patch

from resume_agent.models.resume import BulletPoint, ExperienceEntry, Resume
from resume_agent.pipelines import setup as setup_pipeline
from resume_agent.pipelines.setup import run_review_base
from resume_agent.prompts import rewrite_bullets, suggest_adjacent_skills

EXISTING_RESUME = Resume(
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
            bullets=[
                BulletPoint(original="Already reviewed bullet", variants=["Reviewed variant A", "Reviewed variant B"]),
                BulletPoint(original="Manually added bullet, no variants yet"),
            ],
        ),
    ],
    education=[],
    projects=[],
)


def _fake_message(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


def _fake_create(*, system=None, **kwargs):
    if system == rewrite_bullets.SYSTEM:
        return _fake_message('["Backfilled variant one", "Backfilled variant two"]')
    if system == suggest_adjacent_skills.SYSTEM:
        return _fake_message('{"suggestions": []}')
    raise AssertionError(f"Unexpected system prompt: {system}")


def test_review_only_generates_variants_for_bullets_missing_them(tmp_path, monkeypatch):
    from resume_agent.config import settings

    base_path = tmp_path / "resume_base.md"
    base_path.write_text(setup_pipeline._render_base_md(EXISTING_RESUME))
    monkeypatch.setattr(settings, "base_resume_path", str(base_path))

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = _fake_create

    with patch.object(setup_pipeline.anthropic, "Anthropic", return_value=fake_client):
        run_review_base()

    # One call for the missing-variant bullet, one for the skill-suggestion pass.
    assert fake_client.messages.create.call_count == 2
    rewrite_call = next(
        c
        for c in fake_client.messages.create.call_args_list
        if c.kwargs["system"] == rewrite_bullets.SYSTEM
    )
    assert "Manually added bullet, no variants yet" in rewrite_call.kwargs["messages"][0]["content"]

    refreshed = setup_pipeline._parse_base_md(base_path.read_text())
    bullets = refreshed.experience[0].bullets
    assert bullets[0].variants == ["Reviewed variant A", "Reviewed variant B"]
    assert bullets[1].variants == ["Backfilled variant one", "Backfilled variant two"]
