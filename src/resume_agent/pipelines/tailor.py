from pathlib import Path

import anthropic
from rich import print as rprint
from slugify import slugify

from resume_agent.config import settings
from resume_agent.models.job import JobDescription
from resume_agent.prompts import extract_jd, match_resume, tailor_resume
from resume_agent.tools.page_validator import is_one_page
from resume_agent.tools.pdf_exporter import markdown_to_pdf
from resume_agent.tools.web_scraper import fetch_job_text

import json


def run_tailor(url: str, company: str, role: str) -> Path:
    """
    Per-job pipeline: URL + base resume → tailored PDF.
    Returns path to the output PDF.
    """
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    slug = slugify(f"{company}-{role}")

    # ── Scrape & extract JD ──
    rprint("[bold]Step 1:[/bold] Fetching job description...")
    raw_jd = fetch_job_text(url)

    rprint("[bold]Step 2:[/bold] Extracting structured JD data...")
    msg = client.messages.create(
        model=settings.claude_model,
        max_tokens=2048,
        system=extract_jd.SYSTEM,
        messages=[{"role": "user", "content": extract_jd.build(raw_jd, company, role)}],
    )
    jd_data = json.loads(msg.content[0].text)
    jd = JobDescription(company=company, role=role, url=url, slug=slug, raw_text=raw_jd, **jd_data)

    # Write job.md
    jobs_dir = Path(settings.data_dir) / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    jd_path = jobs_dir / f"{slug}.md"
    jd_path.write_text(_render_jd_md(jd))
    rprint(f"  Saved JD → {jd_path}")

    # ── Load base resume ──
    base_md = Path(settings.base_resume_path).read_text()

    # ── Match & score ──
    rprint("[bold]Step 3:[/bold] Scoring resume-to-JD fit...")
    # (Simplified inline; could be its own prompt module)
    score_msg = client.messages.create(
        model=settings.claude_model,
        max_tokens=512,
        messages=[{"role": "user", "content": (
            f"Score 0.0–1.0 how well this resume matches the job. "
            f"Return JSON: {{\"score\": float, \"notes\": str}}\n\n"
            f"JOB:\n{jd_path.read_text()}\n\nRESUME (excerpt):\n{base_md[:3000]}"
        )}],
    )
    score_data = json.loads(score_msg.content[0].text)
    fit_score: float = score_data["score"]
    fit_notes: str   = score_data["notes"]
    rprint(f"  Fit score: [bold]{fit_score:.0%}[/bold] — {fit_notes}")

    if fit_score < 0.4:
        rprint("[yellow]Warning:[/yellow] Low fit score. Consider adding relevant experience before applying.")

    # ── Tailor & validate ──
    rprint("[bold]Step 4:[/bold] Tailoring resume...")
    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    tailored_md = _tailor_with_page_limit(client, base_md, jd_path.read_text(), fit_score, slug, output_dir)

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
    fit_score: float,
    slug: str,
    output_dir: Path,
) -> str:
    """Tailor the resume, retrying with trim passes until it fits on one page."""
    for trim_pass in range(settings.page_trim_attempts):
        msg = client.messages.create(
            model=settings.claude_model,
            max_tokens=4096,
            system=tailor_resume.SYSTEM,
            messages=[{"role": "user", "content": tailor_resume.build(
                base_md, jd_md, fit_score, trim_pass=trim_pass
            )}],
        )
        tailored_md = msg.content[0].text

        # Quick page check via temp PDF
        tmp_pdf = output_dir / f"_{slug}_tmp.pdf"
        from resume_agent.tools.pdf_exporter import markdown_to_pdf
        markdown_to_pdf(tailored_md, tmp_pdf)

        if is_one_page(tmp_pdf):
            tmp_pdf.unlink(missing_ok=True)
            return tailored_md

        rprint(f"  [yellow]Trim pass {trim_pass + 1}:[/yellow] Output exceeded one page, retrying...")

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
        "## Responsibilities",
        *[f"- {r}" for r in jd.responsibilities],
        "",
        "## ATS Keywords",
        ", ".join(jd.ats_keywords),
    ]
    return "\n".join(lines)