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


def test_tailor_passes_always_include_experience_title_from_settings(tmp_path, monkeypatch):
    from resume_agent.config import settings

    monkeypatch.setattr(settings, "always_include_experience_title", "Professional Poker Player")

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_message("# Resume\n\nfits")

    with (
        patch("resume_agent.pipelines.tailor.markdown_to_pdf", return_value=tmp_path / "x.pdf"),
        patch("resume_agent.pipelines.tailor.is_one_page", return_value=True),
    ):
        _tailor_with_page_limit(fake_client, "base md", "jd md", "slug", tmp_path)

    sent_prompt = fake_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert '"Professional Poker Player"' in sent_prompt
    assert "Always include the Experience entry titled exactly" in sent_prompt


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
    from resume_agent.pipelines import tailor as tailor_pipeline
    from resume_agent.prompts import extract_and_assess
    from resume_agent.tools.resume_markdown import render_base_md

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
    base_path.write_text(render_base_md(base_resume))
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

    # Even on a PASS (no tailoring), the raw scrape and a usage-log row are kept.
    raw_path = tmp_path / "jobs" / "acme-platform-engineer.raw.txt"
    assert raw_path.read_text() == "raw job posting text"

    log_rows = (tmp_path / "usage_log.csv").read_text().splitlines()
    assert log_rows[0] == (
        "date,company,role,verdict,screening_fit_score,final_fit_score,"
        "ats_keywords_found,ats_keywords_total,remaining_gaps,low_relevance_bullets,"
        "refine_rounds"
    )
    _, company, role, verdict, screening_fit_score = log_rows[1].split(",")[:5]
    assert (company, role, verdict, screening_fit_score) == (
        "Acme", "Platform Engineer", "PASS", "0.1",
    )


def test_run_tailor_rejects_scrape_thats_too_short_to_be_a_job_posting(tmp_path, monkeypatch):
    """A near-empty scrape (JS wall, login page, failed scrape) should be rejected
    before any LLM call is made."""
    from resume_agent.config import settings
    from resume_agent.pipelines import tailor as tailor_pipeline

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))

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
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
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
    from resume_agent.pipelines import tailor as tailor_pipeline
    from resume_agent.prompts import extract_and_assess, review_output, tailor_resume
    from resume_agent.tools.resume_markdown import render_base_md

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
    base_path.write_text(render_base_md(base_resume))
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
                        "reason": "Directly names Kubernetes, a required skill.",
                    },
                ],
                "improvement_suggestions": [
                    {
                        "suggestion": "Add 'Spark' to the Skills section.",
                        "evidence": "An unused bullet variant mentions Spark explicitly.",
                        "addresses": "Spark",
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
    assert "Suggestions to Improve Fit & ATS Coverage" in content
    assert "Add 'Spark' to the Skills section." in content
    assert "*Why:* Directly names Kubernetes, a required skill." in content
    # The tailored resume itself must never mention the gap.
    assert "Spark" not in md_path.read_text()

    raw_path = tmp_path / "jobs" / "acme-platform-engineer.raw.txt"
    assert raw_path.read_text() == "raw job posting text"

    log_row = (tmp_path / "usage_log.csv").read_text().splitlines()[1]
    _, company, role, verdict, screening_fit_score, final_fit_score = log_row.split(",")[:6]
    assert (company, role, verdict, screening_fit_score, final_fit_score) == (
        "Acme", "Platform Engineer", "APPLY", "0.8", "0.75",
    )


def test_run_tailor_refines_and_accepts_an_improving_round(tmp_path, monkeypatch):
    """The refine loop should accept a round whose reviewed fit_score beats the
    previous best and keep going, then stop (keeping that best round) as soon as
    a later round fails to improve further — exercising the loop's "it actually
    worked, continue" branch, not just "nothing to act on" / "no improvement"."""
    from resume_agent.config import settings
    from resume_agent.models.resume import BulletPoint, ExperienceEntry, Resume
    from resume_agent.pipelines import tailor as tailor_pipeline
    from resume_agent.prompts import extract_and_assess, refine_resume, review_output, tailor_resume
    from resume_agent.tools.resume_markdown import render_base_md

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
    base_path.write_text(render_base_md(base_resume))
    output_dir = tmp_path / "output"
    monkeypatch.setattr(settings, "base_resume_path", str(base_path))
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "output_dir", str(output_dir))
    monkeypatch.setattr(settings, "min_fit_score", 0.4)
    monkeypatch.setattr(settings, "min_jd_chars", 0)
    monkeypatch.setattr(settings, "max_refine_attempts", 3)

    initial_text = "# Jordan Rivera\n\n## Experience\n- Shipped a thing\n"
    round1_text = "# Jordan Rivera\n\n## Experience\n- Shipped a thing with Spark\n"
    round2_text = "# Jordan Rivera\n\n## Experience\n- Shipped a thing with Spark, again\n"
    # First review (of the initial tailor) scores lowest; round 1 improves on it;
    # round 2 ties round 1's score, so refinement should stop there and keep round 1.
    review_fit_scores = iter([0.6, 0.75, 0.75])

    def _review_response() -> str:
        return json.dumps({
            "fit_score": next(review_fit_scores),
            "reasoning": "x",
            "remaining_gaps": ["Spark"],
            "bullet_reviews": [
                {
                    "bullet": "Shipped a thing",
                    "supports": [],
                    "relevance": "high",
                    "reason": "x",
                },
            ],
            "improvement_suggestions": [
                {
                    "suggestion": "Mention Spark explicitly.",
                    "evidence": "An unused variant mentions Spark.",
                    "addresses": "Spark",
                },
            ],
        })

    refine_texts = iter([round1_text, round2_text])

    def _fake_create(*, system=None, messages=None, **kwargs):
        prompt = messages[0]["content"]
        if system == extract_and_assess.SYSTEM:
            return _fake_message(json.dumps({
                "required_skills": ["Spark"],
                "preferred_skills": [],
                "reinforced_requirements": [],
                "responsibilities": [],
                "ats_keywords": ["Spark"],
                "fit_score": 0.8,
                "reasoning": "Good overlap.",
                "gaps": [],
            }))
        if system == review_output.SYSTEM:
            return _fake_message(_review_response())
        if system == tailor_resume.SYSTEM:
            is_refine = "A prior tailoring attempt was already reviewed" in prompt
            if not is_refine:
                return _fake_message(initial_text)
            return _fake_message(next(refine_texts))
        raise AssertionError(f"Unexpected system prompt: {system}")

    # refine_resume.SYSTEM is literally tailor_resume.SYSTEM (see refine_resume.py) —
    # confirm that assumption holds, since _fake_create's dispatch above depends on it.
    assert refine_resume.SYSTEM == tailor_resume.SYSTEM

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
    # Round 2 tied round 1's score rather than beating it, so round 1 is kept.
    assert md_path.read_text() == round1_text

    log_row = (tmp_path / "usage_log.csv").read_text().splitlines()[1]
    fields = log_row.split(",")
    assert fields[4] == "0.8"  # screening_fit_score (from extract_and_assess)
    assert fields[5] == "0.75"  # final_fit_score (round 1's, not round 2's)
    assert fields[-1] == "1"  # refine_rounds: exactly one round accepted
