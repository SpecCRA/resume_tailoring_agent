"""Per-job pipeline: a posting URL + the base resume -> a tailored, one-page PDF.

`run_tailor` walks five steps: (1) scrape the posting, rejecting it early if it's
too short or the extractor flags it as not an actual job description; (2) extract
it into a structured `JobDescription`; (3) assess resume-to-JD fit against a
variant-free view of the resume, gated by `settings.min_fit_score` — a "pass"
recommendation stops the pipeline here, before either of the more expensive calls
below run; (4) tailor the resume, retrying with trim passes
(`_tailor_with_page_limit`) until the rendered PDF fits one page; (5) export it.
Every step that calls out to an LLM or the network can raise a `ResumeAgentError`
subclass (see `errors.py`) instead of crashing with a raw exception.
"""

from pathlib import Path

import anthropic
import pydantic
from rich import print as rprint
from slugify import slugify

from resume_agent.config import settings
from resume_agent.errors import InvalidJobDescriptionError, LLMResponseError
from resume_agent.models.job import JobDescription
from resume_agent.pipelines.setup import _parse_base_md, _render_originals_only_md
from resume_agent.prompts import assess_fit, extract_jd, tailor_resume
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

    # ── Scrape & extract JD ──
    rprint("[bold]Step 1:[/bold] Fetching job description...")
    raw_jd = fetch_job_text(url)
    if len(raw_jd.strip()) < settings.min_jd_chars:
        raise InvalidJobDescriptionError(
            f"Fetched page from {url} has only {len(raw_jd.strip())} characters of text "
            f"(expected at least {settings.min_jd_chars}) — this doesn't look like a "
            "real job posting. The page may require JavaScript, be behind a login wall, "
            "or the scrape may have failed silently."
        )

    rprint("[bold]Step 2:[/bold] Extracting structured JD data...")
    jd_data = call_llm_json(
        client,
        system=extract_jd.SYSTEM,
        prompt=extract_jd.build(raw_jd, company, role),
        max_tokens=2048,
    )
    if not jd_data.get("looks_like_a_job_posting", True):
        raise InvalidJobDescriptionError(
            f"The content fetched from {url} doesn't look like an actual job "
            "description (e.g. an error page, login wall, or placeholder content)."
        )
    try:
        jd = JobDescription(
            company=company, role=role, url=url, slug=slug, raw_text=raw_jd, **jd_data
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

    # ── Load base resume ──
    base_md = Path(settings.base_resume_path).read_text()

    # ── Assess fit ──
    rprint("[bold]Step 3:[/bold] Assessing resume-to-JD fit...")
    resume_for_assessment = _render_originals_only_md(_parse_base_md(base_md))
    fit = call_llm_json(
        client,
        system=assess_fit.SYSTEM,
        prompt=assess_fit.build(resume_for_assessment, jd_path.read_text()),
        max_tokens=512,
    )
    should_apply = fit["fit_score"] >= settings.min_fit_score
    rprint(f"  Assessment: [bold]{'APPLY' if should_apply else 'PASS'}[/bold] — {fit['reasoning']}")

    if not should_apply:
        rprint("[yellow]Skipping tailoring — recommendation is PASS.[/yellow]")
        return None

    # ── Tailor & validate ──
    rprint("[bold]Step 4:[/bold] Tailoring resume...")
    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    tailored_md = _tailor_with_page_limit(
        client, base_md, jd_path.read_text(), fit["gaps"], slug, output_dir
    )

    # Write final markdown
    md_path = output_dir / f"{slug}.md"
    md_path.write_text(tailored_md)
    rprint(f"  Saved tailored resume → {md_path}")

    # Export to PDF
    rprint("[bold]Step 5:[/bold] Exporting to PDF...")
    pdf_path = markdown_to_pdf(tailored_md, output_dir / f"{slug}.pdf")
    rprint(f"[green]Done![/green] PDF → {pdf_path}")
    return pdf_path


def _tailor_with_page_limit(
    client: anthropic.Anthropic,
    base_md: str,
    jd_md: str,
    gaps: list[str],
    slug: str,
    output_dir: Path,
) -> str:
    """Tailor the resume, retrying with trim passes until it fits on one page."""
    for trim_pass in range(settings.page_trim_attempts):
        tailored_md = call_llm_text(
            client,
            system=tailor_resume.SYSTEM,
            prompt=tailor_resume.build(base_md, jd_md, gaps, trim_pass=trim_pass),
            max_tokens=4096,
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
