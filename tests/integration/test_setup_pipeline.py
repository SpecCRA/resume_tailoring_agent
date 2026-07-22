import inspect
import json
from unittest.mock import MagicMock, patch

from resume_agent.pipelines import setup as setup_pipeline
from resume_agent.pipelines.setup import run_setup
from resume_agent.prompts import parse_resume, rewrite_bullets
from resume_agent.tools.page_validator import count_pages
from resume_agent.tools.pdf_exporter import markdown_to_pdf

# A resume with far more content than could ever fit on one page, to prove
# the setup pipeline doesn't trim anything down to a page limit.
BIG_RESUME = {
    "name": "Jordan Rivera",
    "email": "jordan@example.com",
    "phone": "555-0100",
    "linkedin": None,
    "github": None,
    "location": "Remote",
    "summary": "Senior engineer with a decade of experience across many domains.",
    "skills": [f"Skill {i}" for i in range(30)],
    "experience": [
        {
            "company": f"Company {i}",
            "title": "Senior Engineer",
            "dates": "2015-2020",
            "location": "Remote",
            "bullets": [
                {"original": f"Delivered impactful project {i}-{j} with measurable results"}
                for j in range(6)
            ],
        }
        for i in range(6)
    ],
    "education": [
        {
            "institution": "State University",
            "degree": "B.S. Computer Science",
            "dates": "2011-2015",
            "gpa": 3.8,
        }
    ],
    "projects": [
        {
            "name": f"Project {i}",
            "description": "A substantial side project demonstrating range.",
            "bullets": [
                {"original": f"Built feature {i}-{j} end to end"} for j in range(4)
            ],
            "url": None,
        }
        for i in range(4)
    ],
}


def _fake_message(text: str):
    block = MagicMock()
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


def _fake_create(*, system, **kwargs):
    if system == parse_resume.SYSTEM:
        return _fake_message(json.dumps(BIG_RESUME))
    if system == rewrite_bullets.SYSTEM:
        return _fake_message(json.dumps(["variant one", "variant two", "variant three"]))
    raise AssertionError(f"Unexpected system prompt: {system}")


def test_base_resume_is_not_trimmed_to_one_page(tmp_path, monkeypatch):
    """setup.py must never enforce a page limit — that's the tailor pipeline's job."""
    from resume_agent.config import settings

    monkeypatch.setattr(settings, "base_resume_path", str(tmp_path / "resume_base.md"))
    monkeypatch.setattr(setup_pipeline, "extract_text", lambda _: "raw resume text")

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = _fake_create

    with patch.object(setup_pipeline.anthropic, "Anthropic", return_value=fake_client):
        base_path = run_setup("unused.pdf")

    base_md = base_path.read_text()
    pdf_path = markdown_to_pdf(base_md, tmp_path / "base_resume.pdf")

    assert count_pages(pdf_path) > 1, (
        "Base resume was trimmed to one page — the one-page constraint must only "
        "apply to the tailored output, not the base resume."
    )


def test_setup_pipeline_never_invokes_page_validator():
    """Static guard: setup.py must not depend on the page validator at all."""
    source = inspect.getsource(setup_pipeline)
    assert "page_validator" not in source
    assert "is_one_page" not in source
