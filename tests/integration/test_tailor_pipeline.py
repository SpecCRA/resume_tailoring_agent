import json
from unittest.mock import MagicMock, patch

import pytest

from resume_agent.errors import InvalidJobDescriptionError
from resume_agent.pipelines.tailor import _tailor_with_page_limit, run_tailor


def _fake_message(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


def test_tailored_resume_retries_until_it_fits_one_page(tmp_path):
    """Only the tailored output is held to a one-page limit, with trim retries."""
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = [
        _fake_message("# Resume\n\ntoo long, pass 0"),
        _fake_message("# Resume\n\ntoo long, pass 1"),
        _fake_message("# Resume\n\nfinally fits, pass 2"),
    ]

    # First two page checks report multi-page output, third reports one page.
    page_results = iter([False, False, True])

    with (
        patch("resume_agent.pipelines.tailor.markdown_to_pdf", return_value=tmp_path / "x.pdf"),
        patch("resume_agent.pipelines.tailor.is_one_page", side_effect=lambda p: next(page_results)),
    ):
        result = _tailor_with_page_limit(fake_client, "base md", "jd md", "slug", tmp_path)

    assert result == "# Resume\n\nfinally fits, pass 2"
    assert fake_client.messages.create.call_count == 3


def test_tailor_gives_up_after_max_attempts_and_returns_last_output(tmp_path, monkeypatch):
    from resume_agent.config import settings

    monkeypatch.setattr(settings, "page_trim_attempts", 2)

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = [
        _fake_message("# Resume\n\nattempt 0"),
        _fake_message("# Resume\n\nattempt 1"),
    ]

    with (
        patch("resume_agent.pipelines.tailor.markdown_to_pdf", return_value=tmp_path / "x.pdf"),
        patch("resume_agent.pipelines.tailor.is_one_page", return_value=False),
    ):
        result = _tailor_with_page_limit(fake_client, "base md", "jd md", "slug", tmp_path)

    assert result == "# Resume\n\nattempt 1"
    assert fake_client.messages.create.call_count == 2


def test_run_tailor_skips_tailoring_when_assessment_recommends_pass(tmp_path, monkeypatch):
    """A below-threshold fit assessment should short-circuit before any tailoring
    or PDF-export work happens."""
    from resume_agent.config import settings
    from resume_agent.models.resume import BulletPoint, ExperienceEntry, Resume
    from resume_agent.pipelines import setup as setup_pipeline
    from resume_agent.pipelines import tailor as tailor_pipeline
    from resume_agent.prompts import extract_and_assess

    base_resume = Resume(
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
    base_path = tmp_path / "resume_base.md"
    base_path.write_text(setup_pipeline._render_base_md(base_resume))
    monkeypatch.setattr(settings, "base_resume_path", str(base_path))
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "output_dir", str(tmp_path / "output"))
    monkeypatch.setattr(settings, "min_fit_score", 0.4)
    monkeypatch.setattr(settings, "min_jd_chars", 0)

    def _fake_create(*, system=None, **kwargs):
        if system == extract_and_assess.SYSTEM:
            return _fake_message(json.dumps({
                "required_skills": ["Kubernetes"],
                "preferred_skills": [],
                "reinforced_requirements": [],
                "responsibilities": ["Run large-scale infra"],
                "ats_keywords": ["kubernetes"],
                "fit_score": 0.1,
                "reasoning": "Not enough overlap with core infra requirements.",
                "gaps": ["Kubernetes", "Spark"],
            }))
        raise AssertionError(f"Unexpected system prompt: {system}")

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = _fake_create

    with (
        patch.object(tailor_pipeline.anthropic, "Anthropic", return_value=fake_client),
        patch("resume_agent.pipelines.tailor.fetch_job_text", return_value="raw job posting text"),
        patch("resume_agent.pipelines.tailor.markdown_to_pdf") as mock_export,
    ):
        result = run_tailor("https://example.com/job", "Acme", "Platform Engineer")

    assert result is None
    # Only the merged extract+assess call should run — tailoring is skipped entirely.
    assert fake_client.messages.create.call_count == 1
    mock_export.assert_not_called()


def test_run_tailor_rejects_scrape_thats_too_short_to_be_a_job_posting(tmp_path):
    """A near-empty scrape (JS wall, login page, failed scrape) should be rejected
    before any LLM call is made."""
    from resume_agent.pipelines import tailor as tailor_pipeline

    fake_client = MagicMock()

    with (
        patch.object(tailor_pipeline.anthropic, "Anthropic", return_value=fake_client),
        patch("resume_agent.pipelines.tailor.fetch_job_text", return_value="Enable JS"),
    ):
        with pytest.raises(InvalidJobDescriptionError):
            run_tailor("https://example.com/job", "Acme", "Platform Engineer")

    assert fake_client.messages.create.call_count == 0


def test_run_tailor_rejects_content_flagged_as_not_a_job_posting(tmp_path, monkeypatch):
    """Even scraped text that's long enough can turn out not to be an actual job
    description (e.g. a long cookie-consent/login-wall page) — the combined
    extract+assess call's own judgment should stop the pipeline before tailoring."""
    from resume_agent.config import settings
    from resume_agent.pipelines import tailor as tailor_pipeline
    from resume_agent.prompts import extract_and_assess

    monkeypatch.setattr(settings, "base_resume_path", str(tmp_path / "resume_base.md"))
    (tmp_path / "resume_base.md").write_text("# Jordan Rivera\n\n## Experience\n")

    def _fake_create(*, system=None, **kwargs):
        if system == extract_and_assess.SYSTEM:
            return _fake_message(json.dumps({
                "looks_like_a_job_posting": False,
                "required_skills": [],
                "preferred_skills": [],
                "reinforced_requirements": [],
                "responsibilities": [],
                "ats_keywords": [],
                "fit_score": 0.0,
                "reasoning": "Not a real job posting.",
                "gaps": [],
            }))
        raise AssertionError(f"Unexpected system prompt: {system}")

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = _fake_create

    with (
        patch.object(tailor_pipeline.anthropic, "Anthropic", return_value=fake_client),
        patch("resume_agent.pipelines.tailor.fetch_job_text", return_value="x" * 500),
    ):
        with pytest.raises(InvalidJobDescriptionError):
            run_tailor("https://example.com/job", "Acme", "Platform Engineer")

    assert fake_client.messages.create.call_count == 1


def test_run_tailor_writes_assessment_report(tmp_path, monkeypatch):
    """After a successful tailor run, Step 5 should write output/<slug>.assessment.md
    with a fit score, ATS keyword coverage, and per-bullet relevance sections —
    and must never touch the tailored resume's own .md/.pdf files."""
    from resume_agent.config import settings
    from resume_agent.models.resume import BulletPoint, ExperienceEntry, Resume
    from resume_agent.pipelines import setup as setup_pipeline
    from resume_agent.pipelines import tailor as tailor_pipeline
    from resume_agent.prompts import extract_and_assess, review_output, tailor_resume

    base_resume = Resume(
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
    base_path = tmp_path / "resume_base.md"
    base_path.write_text(setup_pipeline._render_base_md(base_resume))
    output_dir = tmp_path / "output"
    monkeypatch.setattr(settings, "base_resume_path", str(base_path))
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "output_dir", str(output_dir))
    monkeypatch.setattr(settings, "min_fit_score", 0.4)
    monkeypatch.setattr(settings, "min_jd_chars", 0)

    tailored_text = "# Jordan Rivera\n\n## Experience\n- Shipped a thing with Kubernetes\n"

    def _fake_create(*, system=None, **kwargs):
        if system == extract_and_assess.SYSTEM:
            return _fake_message(json.dumps({
                "required_skills": ["Kubernetes"],
                "preferred_skills": [],
                "reinforced_requirements": [],
                "responsibilities": ["Run large-scale infra"],
                "ats_keywords": ["Kubernetes", "Spark"],
                "fit_score": 0.8,
                "reasoning": "Strong overlap with infra requirements.",
                "gaps": ["Spark"],
            }))
        if system == tailor_resume.SYSTEM:
            return _fake_message(tailored_text)
        if system == review_output.SYSTEM:
            return _fake_message(json.dumps({
                "fit_score": 0.75,
                "reasoning": "Good match overall.",
                "remaining_gaps": ["Spark"],
                "bullet_reviews": [
                    {
                        "bullet": "Shipped a thing with Kubernetes",
                        "supports": ["Kubernetes"],
                        "relevance": "high",
                    },
                ],
            }))
        raise AssertionError(f"Unexpected system prompt: {system}")

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = _fake_create

    with (
        patch.object(tailor_pipeline.anthropic, "Anthropic", return_value=fake_client),
        patch("resume_agent.pipelines.tailor.fetch_job_text", return_value="raw job posting text"),
        patch("resume_agent.pipelines.tailor.markdown_to_pdf", return_value=tmp_path / "x.pdf"),
        patch("resume_agent.pipelines.tailor.is_one_page", return_value=True),
    ):
        result = tailor_pipeline.run_tailor("https://example.com/job", "Acme", "Platform Engineer")

    assert result == tmp_path / "x.pdf"

    md_path = output_dir / "acme-platform-engineer.md"
    assert md_path.read_text() == tailored_text

    assessment_path = output_dir / "acme-platform-engineer.assessment.md"
    assert assessment_path.exists()
    content = assessment_path.read_text()
    assert "0.75" in content
    assert "ATS Keyword Coverage (1/2)" in content
    assert "Shipped a thing with Kubernetes" in content
    assert "### High" in content
    assert "Gaps Flagged at Screening" in content
    assert "- Spark" in content
    assert "Remaining Gaps (after tailoring)" in content
    # The tailored resume itself must never mention the gap.
    assert "Spark" not in md_path.read_text()
