import json
from unittest.mock import MagicMock

import pytest

from resume_agent.errors import LLMResponseError
from resume_agent.models.resume import BulletPoint, ExperienceEntry, ProjectEntry, Resume
from resume_agent.pipelines.setup import _generate_all_bullet_variants


def _fake_message(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


def _resume_with_bullets(*bullets: str) -> Resume:
    return Resume(
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
                bullets=[BulletPoint(original=b) for b in bullets],
            ),
        ],
        education=[],
        projects=[],
    )


def test_generate_all_bullet_variants_batches_into_a_single_call():
    resume = _resume_with_bullets("Shipped a thing", "Fixed a bug")
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_message(json.dumps({
        "bullets": [
            {"id": 0, "variants": ["v0a", "v0b"]},
            {"id": 1, "variants": ["v1a", "v1b"]},
        ]
    }))

    _generate_all_bullet_variants(fake_client, resume)

    assert fake_client.messages.create.call_count == 1
    assert resume.experience[0].bullets[0].variants == ["v0a", "v0b"]
    assert resume.experience[0].bullets[1].variants == ["v1a", "v1b"]


def test_generate_all_bullet_variants_raises_on_missing_id_in_response():
    resume = _resume_with_bullets("Shipped a thing", "Fixed a bug")
    fake_client = MagicMock()
    # Only id 0 comes back — id 1 is missing from the response.
    fake_client.messages.create.return_value = _fake_message(json.dumps({
        "bullets": [{"id": 0, "variants": ["v0a", "v0b"]}]
    }))

    with pytest.raises(LLMResponseError):
        _generate_all_bullet_variants(fake_client, resume)


def test_generate_all_bullet_variants_skips_call_when_nothing_is_missing():
    resume = _resume_with_bullets("Shipped a thing")
    resume.experience[0].bullets[0].variants = ["already there"]
    fake_client = MagicMock()

    _generate_all_bullet_variants(fake_client, resume)

    assert fake_client.messages.create.call_count == 0


def test_generate_all_bullet_variants_flags_only_the_first_experience_entry():
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
                company="Current Co",
                title="Staff Engineer",
                dates="2023-Present",
                bullets=[BulletPoint(original="Most recent role bullet")],
            ),
            ExperienceEntry(
                company="Old Co",
                title="Engineer",
                dates="2019-2023",
                bullets=[BulletPoint(original="Older role bullet")],
            ),
        ],
        education=[],
        projects=[
            ProjectEntry(name="Side Project", bullets=[BulletPoint(original="Project bullet")])
        ],
    )
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_message(json.dumps({
        "bullets": [
            {"id": 0, "variants": ["v0"]},
            {"id": 1, "variants": ["v1"]},
            {"id": 2, "variants": ["v2"]},
        ]
    }))

    _generate_all_bullet_variants(fake_client, resume)

    sent_prompt = fake_client.messages.create.call_args.kwargs["messages"][0]["content"]
    items = json.loads(sent_prompt.split("Bullets to rewrite:\n")[1].split("\n\nReturn")[0])
    by_bullet_text = {item["bullet"]: item["is_most_recent"] for item in items}
    assert by_bullet_text["Most recent role bullet"] is True
    assert by_bullet_text["Older role bullet"] is False
    assert by_bullet_text["Project bullet"] is False
