"""Per-job pipeline: a posting URL + the base resume -> a tailored, one-page PDF.

`run_tailor` walks five steps: (1) scrape the posting, rejecting it early if it's
too short; (2) extract it into a structured `JobDescription` AND assess
resume-to-JD fit against a variant-free view of the resume in the same call
(`prompts/extract_and_assess.py`) — rejecting early if the extractor flags the
content as not an actual job description, and gated by `settings.min_fit_score` —
a "pass" recommendation stops the pipeline here, before the more expensive tailoring
call below runs; (3) tailor the resume, retrying with trim passes
(`_tailor_with_page_limit`) until the rendered PDF fits one page; (4) export it;
(5) review the finished resume against the JD — a holistic fit score plus a
per-bullet relevance breakdown and a deterministic ATS keyword coverage check —
written to its own `<slug>.assessment.md` report, never appended into the resume
itself. Every step that calls out to an LLM or the network can raise a
`ResumeAgentError` subclass (see `errors.py`) instead of crashing with a raw
exception.

Gaps between resume and JD are never written into the resume — `tailor_resume`
isn't even told about them. Both the gaps flagged at screening (step 2, before
tailoring) and the gaps still remaining after tailoring (step 5, from
`review_output`) are surfaced only in the assessment report.
"""

import re
from pathlib import Path
from typing import Any

import anthropic
import pydantic
from rich import print as rprint
from slugify import slugify

from resume_agent.config import settings
from resume_agent.errors import InvalidJobDescriptionError, LLMResponseError
from resume_agent.models.job import JobDescription
from resume_agent.pipelines.setup import _parse_base_md, _render_originals_only_md
from resume_agent.prompts import extract_and_assess, review_output, tailor_resume
from resume_agent.tools.llm import call_llm_json, call_llm_text
from resume_agent.tools.page_validator import is_one_page
from resume_agent.tools.pdf_exporter import markdown_to_pdf
from resume_agent.tools.web_scraper import fetch_job_text


def run_tailor(url: str, company: str, role: str) -> Path | None:
    """
    Per-job pipeline: URL + base resume → tailored PDF.
    Returns path to the output PDF, or None if the fit assessment recommends
    passing on this job (tailoring is skipped entirely in that case).
    """
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    slug = slugify(f"{company}-{role}")

    # ── Scrape ──
    rprint("[bold]Step 1:[/bold] Fetching job description...")
    raw_jd = fetch_job_text(url)
    if len(raw_jd.strip()) < settings.min_jd_chars:
        raise InvalidJobDescriptionError(
            f"Fetched page from {url} has only {len(raw_jd.strip())} characters of text "
            f"(expected at least {settings.min_jd_chars}) — this doesn't look like a "
            "real job posting. The page may require JavaScript, be behind a login wall, "
            "or the scrape may have failed silently."
        )

    # ── Load base resume ──
    base_md = Path(settings.base_resume_path).read_text()
    resume_for_assessment = _render_originals_only_md(_parse_base_md(base_md))

    # ── Extract JD and assess fit, in one call ──
    rprint("[bold]Step 2:[/bold] Extracting JD data and assessing fit...")
    data = call_llm_json(
        client,
        system=extract_and_assess.SYSTEM,
        prompt=extract_and_assess.build(raw_jd, company, role, resume_for_assessment),
        max_tokens=2560,
    )
    if not data.get("looks_like_a_job_posting", True):
        raise InvalidJobDescriptionError(
            f"The content fetched from {url} doesn't look like an actual job "
            "description (e.g. an error page, login wall, or placeholder content)."
        )
    try:
        jd = JobDescription(
            company=company, role=role, url=url, slug=slug, raw_text=raw_jd, **data
        )
    except pydantic.ValidationError as e:
        raise LLMResponseError(
            f"The JD extractor returned data that didn't match the expected shape: {e}"
        ) from e

    # Write job.md
    jobs_dir = Path(settings.data_dir) / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    jd_path = jobs_dir / f"{slug}.md"
    jd_path.write_text(_render_jd_md(jd))
    rprint(f"  Saved JD → {jd_path}")

    should_apply = data["fit_score"] >= settings.min_fit_score
    verdict = "APPLY" if should_apply else "PASS"
    rprint(f"  Assessment: [bold]{verdict}[/bold] — {data['reasoning']}")

    if not should_apply:
        rprint("[yellow]Skipping tailoring — recommendation is PASS.[/yellow]")
        return None

    # ── Tailor & validate ──
    rprint("[bold]Step 3:[/bold] Tailoring resume...")
    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    tailored_md = _tailor_with_page_limit(
        client, base_md, jd_path.read_text(), slug, output_dir
    )

    # Write final markdown
    md_path = output_dir / f"{slug}.md"
    md_path.write_text(tailored_md)
    rprint(f"  Saved tailored resume → {md_path}")

    # Export to PDF
    rprint("[bold]Step 4:[/bold] Exporting to PDF...")
    pdf_path = markdown_to_pdf(tailored_md, output_dir / f"{slug}.pdf")
    rprint(f"[green]Done![/green] PDF → {pdf_path}")

    # ── Review finished output ──
    rprint("[bold]Step 5:[/bold] Reviewing tailored output...")
    review = call_llm_json(
        client,
        system=review_output.SYSTEM,
        prompt=review_output.build(tailored_md, jd_path.read_text()),
        max_tokens=2048,
    )
    found, missing = _ats_keyword_coverage(tailored_md, jd.ats_keywords)
    assessment_path = output_dir / f"{slug}.assessment.md"
    assessment_path.write_text(
        _render_assessment_md(jd, review, found, missing, data["gaps"])
    )
    low_count = sum(1 for b in review["bullet_reviews"] if b["relevance"] == "low")
    rprint(
        f"  Final fit: [bold]{review['fit_score']}[/bold] | "
        f"ATS coverage: {len(found)}/{len(jd.ats_keywords)} | "
        f"Remaining gaps: {len(review['remaining_gaps'])} | "
        f"Low-relevance bullets: {low_count}"
    )
    rprint(f"  Saved assessment → {assessment_path}")

    return pdf_path


def _tailor_with_page_limit(
    client: anthropic.Anthropic,
    base_md: str,
    jd_md: str,
    slug: str,
    output_dir: Path,
) -> str:
    """Tailor the resume, retrying with trim passes until it fits on one page."""
    for trim_pass in range(settings.page_trim_attempts):
        tailored_md = call_llm_text(
            client,
            system=tailor_resume.SYSTEM,
            prompt=tailor_resume.build(base_md, jd_md, trim_pass=trim_pass),
            max_tokens=8192,
            effort="low",
        )

        # Quick page check via temp PDF
        tmp_pdf = output_dir / f"_{slug}_tmp.pdf"
        markdown_to_pdf(tailored_md, tmp_pdf)

        if is_one_page(tmp_pdf):
            tmp_pdf.unlink(missing_ok=True)
            return tailored_md

        rprint(
            f"  [yellow]Trim pass {trim_pass + 1}:[/yellow] Output exceeded one page, retrying..."
        )

    tmp_pdf.unlink(missing_ok=True)
    rprint("[red]Warning:[/red] Could not fit to one page after max attempts. Using last output.")
    return tailored_md


def _render_jd_md(jd: JobDescription) -> str:
    lines = [
        f"# {jd.role} — {jd.company}",
        f"URL: {jd.url}",
        "",
        "## Required Skills",
        *[f"- {s}" for s in jd.required_skills],
        "",
        "## Preferred Skills",
        *[f"- {s}" for s in jd.preferred_skills],
        "",
        "## Reinforced Requirements (repeated in both sections — likely interview focus)",
        *[f"- {s}" for s in jd.reinforced_requirements],
        "",
        "## Responsibilities",
        *[f"- {r}" for r in jd.responsibilities],
        "",
        "## ATS Keywords",
        ", ".join(jd.ats_keywords),
    ]
    return "\n".join(lines)


_ALTERNATION_RE = re.compile(r"\s+or\s+|/", re.IGNORECASE)


def _keyword_alternatives(keyword: str) -> list[str]:
    """Split a compound keyword like 'ETL/ELT' or 'Spark or Flink' into the
    individual alternatives a JD author meant as interchangeable, so coverage
    counts a hit if the resume literally contains any ONE of them — postings
    routinely list acceptable equivalents this way (ETL/ELT, CI/CD, batch/
    streaming, "Spark or Flink", "AWS/GCP/Azure").

    Guards against degenerate splits like "A/B testing" (which would otherwise
    yield a bare "A") by only splitting when every resulting piece is at least
    two characters — short of that, the "/" is probably part of the term
    itself rather than a separator between two independent keywords.
    """
    parts = [p.strip() for p in _ALTERNATION_RE.split(keyword) if p.strip()]
    if len(parts) > 1 and all(len(p) >= 2 for p in parts):
        return parts
    return [keyword]


def _ats_keyword_coverage(tailored_md: str, ats_keywords: list[str]) -> tuple[list[str], list[str]]:
    """Case-insensitive substring check of which `ats_keywords` literally appear in
    the tailored markdown — each keyword first expanded into its alternatives (see
    `_keyword_alternatives`) so a match on any one equivalent term counts. Still
    deterministic and LLM-free — coverage is a claim about literal string matches,
    not something to trust an LLM's judgment on.
    Returns (found, missing), each preserving the order of `ats_keywords`.
    """
    haystack = tailored_md.lower()
    found = []
    missing = []
    for kw in ats_keywords:
        if any(alt.lower() in haystack for alt in _keyword_alternatives(kw)):
            found.append(kw)
        else:
            missing.append(kw)
    return found, missing


def _render_assessment_md(
    jd: JobDescription,
    review: dict[str, Any],
    found: list[str],
    missing: list[str],
    screening_gaps: list[str],
) -> str:
    by_relevance: dict[str, list[dict[str, Any]]] = {"high": [], "medium": [], "low": []}
    for b in review["bullet_reviews"]:
        by_relevance.setdefault(b["relevance"], []).append(b)

    def _bullet_lines(bullets: list[dict[str, Any]]) -> list[str]:
        if not bullets:
            return ["(none)"]
        return [
            f"- {b['bullet']} — supports: {', '.join(b['supports']) if b['supports'] else '(none)'}"
            for b in bullets
        ]

    lines = [
        f"# Assessment — {jd.role} @ {jd.company}",
        "",
        "## Fit Score",
        f"{review['fit_score']} — {review['reasoning']}",
        "",
        "## Gaps Flagged at Screening (before tailoring)",
        *([f"- {g}" for g in screening_gaps] or ["None flagged."]),
        "",
        "## Remaining Gaps (after tailoring)",
        *([f"- {g}" for g in review["remaining_gaps"]] or ["None flagged."]),
        "",
        f"## ATS Keyword Coverage ({len(found)}/{len(found) + len(missing)})",
        "### Present",
        *([f"- {kw}" for kw in found] or ["(none)"]),
        "### Missing",
        *([f"- {kw}" for kw in missing] or ["(none)"]),
        "",
        "## Bullet Relevance Review",
        "### High",
        *_bullet_lines(by_relevance["high"]),
        "### Medium",
        *_bullet_lines(by_relevance["medium"]),
        "### Low",
        *_bullet_lines(by_relevance["low"]),
    ]
    return "\n".join(lines)
