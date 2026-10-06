"""Per-job pipeline: a posting URL + the base resume -> a tailored, one-page PDF.

`run_tailor` walks six steps: (1) scrape the posting, rejecting it early if it's
too short; (2) extract it into a structured `JobDescription` AND assess
resume-to-JD fit against a variant-free view of the resume in the same call
(`prompts/extract_and_assess.py`) — rejecting early if the extractor flags the
content as not an actual job description, and gated by `settings.min_fit_score` —
a "pass" recommendation stops the pipeline here, before the more expensive tailoring
call below runs; (3) tailor the resume, retrying with trim passes
(`_tailor_with_page_limit`) until the rendered PDF fits one page; (4) review the
tailored output against the JD — a holistic fit score, a per-bullet relevance
breakdown (each with a one-line reason), a deterministic ATS keyword coverage
check, and evidence-grounded suggestions for improving fit/ATS coverage from
content already present elsewhere in the full base resume (an unused bullet
variant, an unlisted-but-demonstrated skill); (5) refine: feed that review's own
`remaining_gaps`/`improvement_suggestions` back into another tailor+review round
(`_refine_until_no_improvement`), repeating until a round fails to beat the best
fit_score found so far or `settings.max_refine_attempts` is reached — so the
output keeps improving instead of stopping at the first attempt, bounded so it
can't loop forever chasing noise; (6) export the best round found to PDF and
write the assessment report. Every step that calls out to an LLM or the network
can raise a `ResumeAgentError` subclass (see `errors.py`) instead of crashing
with a raw exception.

Both LLM-produced JSON shapes this pipeline depends on (the extract+assess result
and the review result) are validated immediately via `models/job.py`'s
`ExtractAndAssessResult` and `models/review.py`'s `TailoredResumeReview` — the
same fail-fast pattern `pipelines/setup.py`/`pipelines/critique.py` already use
for their own LLM output, so a malformed response is a clean `LLMResponseError`
at the call site instead of a bare `KeyError` surfacing later during rendering
or the refine loop. Both are immediately `.model_dump()`'d back to plain dicts
so the rest of this module (rendering, the usage log) keeps working with the
same dict-indexing it always has.

Gaps between resume and JD are never written into the resume — `tailor_resume`
isn't even told about them. Both the gaps flagged at screening (step 2, before
tailoring) and the gaps still remaining after the final refinement round (from
`review_output`) are surfaced only in the assessment report.

Two records persist beyond a single run's output files: the raw scraped text
is saved to `<slug>.raw.txt` right after step 1 (even on a too-short scrape,
since that's exactly the case worth inspecting), and `tools/usage_log.py`
appends one row per invocation to `<data_dir>/usage_log.csv` — date, company,
role, and every assessment number produced (screening fit score, and, if
tailoring ran, final fit score/ATS coverage/remaining gaps/low-relevance
bullets/refinement rounds accepted) — a running history across every job this
has been pointed at, not just the latest one.
"""

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import anthropic
import pydantic
from rich import print as rprint
from slugify import slugify

from resume_agent.config import settings
from resume_agent.errors import InvalidJobDescriptionError, LLMResponseError
from resume_agent.models.job import ExtractAndAssessResult, JobDescription
from resume_agent.models.review import TailoredResumeReview
from resume_agent.prompts import extract_and_assess, refine_resume, review_output, tailor_resume
from resume_agent.tools.ats_matching import ats_keyword_coverage
from resume_agent.tools.llm import call_llm_json, call_llm_text
from resume_agent.tools.page_validator import is_one_page
from resume_agent.tools.pdf_exporter import markdown_to_pdf
from resume_agent.tools.resume_markdown import parse_base_md, render_originals_only_md
from resume_agent.tools.usage_log import append_usage_log
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
    jobs_dir = Path(settings.data_dir) / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    raw_jd = fetch_job_text(url)
    # Saved before the length check below, not after — a too-short scrape is
    # exactly the case where having the raw capture on disk to inspect matters most.
    raw_jd_path = jobs_dir / f"{slug}.raw.txt"
    raw_jd_path.write_text(raw_jd)
    rprint(f"  Saved raw scraped text → {raw_jd_path}")
    if len(raw_jd.strip()) < settings.min_jd_chars:
        raise InvalidJobDescriptionError(
            f"Fetched page from {url} has only {len(raw_jd.strip())} characters of text "
            f"(expected at least {settings.min_jd_chars}) — this doesn't look like a "
            "real job posting. The page may require JavaScript, be behind a login wall, "
            "or the scrape may have failed silently."
        )

    # ── Load base resume ──
    base_md = Path(settings.base_resume_path).read_text()
    resume_for_assessment = render_originals_only_md(parse_base_md(base_md))

    # ── Extract JD and assess fit, in one call ──
    rprint("[bold]Step 2:[/bold] Extracting JD data and assessing fit...")
    data = _call_extract_and_assess(client, raw_jd, company, role, resume_for_assessment)
    if not data["looks_like_a_job_posting"]:
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
    jd_path = jobs_dir / f"{slug}.md"
    jd_path.write_text(_render_jd_md(jd))
    rprint(f"  Saved JD → {jd_path}")

    should_apply = data["fit_score"] >= settings.min_fit_score
    verdict = "APPLY" if should_apply else "PASS"
    rprint(f"  Assessment: [bold]{verdict}[/bold] — {data['reasoning']}")

    if not should_apply:
        rprint("[yellow]Skipping tailoring — recommendation is PASS.[/yellow]")
        append_usage_log(
            {
                "date": date.today().isoformat(),
                "company": company,
                "role": role,
                "verdict": verdict,
                "screening_fit_score": data["fit_score"],
                "final_fit_score": "",
                "ats_keywords_found": "",
                "ats_keywords_total": "",
                "remaining_gaps": "",
                "low_relevance_bullets": "",
                "refine_rounds": "",
            }
        )
        return None

    # ── Tailor ──
    rprint("[bold]Step 3:[/bold] Tailoring resume...")
    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    jd_md = jd_path.read_text()

    tailored_md = _tailor_with_page_limit(client, base_md, jd_md, slug, output_dir)

    # ── Review ──
    rprint("[bold]Step 4:[/bold] Reviewing tailored output...")
    review = _call_review_output(client, tailored_md, jd_md, base_md)
    found, missing = ats_keyword_coverage(tailored_md, jd.ats_keywords)
    rprint(f"  Fit: [bold]{review['fit_score']}[/bold] — {review['reasoning']}")

    # ── Refine: feed the review's own findings back in until it stops helping ──
    tailored_md, review, found, missing, refine_rounds = _refine_until_no_improvement(
        client, base_md, jd_md, jd, tailored_md, review, found, missing, slug, output_dir
    )

    # Write final markdown + PDF (the best round found, not necessarily the first)
    md_path = output_dir / f"{slug}.md"
    md_path.write_text(tailored_md)
    rprint(f"  Saved tailored resume → {md_path}")

    rprint("[bold]Step 6:[/bold] Exporting to PDF...")
    pdf_path = markdown_to_pdf(tailored_md, output_dir / f"{slug}.pdf")
    rprint(f"[green]Done![/green] PDF → {pdf_path}")

    assessment_path = output_dir / f"{slug}.assessment.md"
    assessment_path.write_text(
        _render_assessment_md(jd, review, found, missing, data["gaps"])
    )
    low_count = sum(1 for b in review["bullet_reviews"] if b["relevance"] == "low")
    rprint(
        f"  Final fit: [bold]{review['fit_score']}[/bold] | "
        f"ATS coverage: {len(found)}/{len(jd.ats_keywords)} | "
        f"Remaining gaps: {len(review['remaining_gaps'])} | "
        f"Low-relevance bullets: {low_count} | "
        f"Refinement rounds accepted: {refine_rounds}"
    )
    rprint(f"  Saved assessment → {assessment_path}")

    append_usage_log(
        {
            "date": date.today().isoformat(),
            "company": company,
            "role": role,
            "verdict": verdict,
            "screening_fit_score": data["fit_score"],
            "final_fit_score": review["fit_score"],
            "ats_keywords_found": len(found),
            "ats_keywords_total": len(jd.ats_keywords),
            "remaining_gaps": len(review["remaining_gaps"]),
            "low_relevance_bullets": low_count,
            "refine_rounds": refine_rounds,
        }
    )

    return pdf_path


def _call_extract_and_assess(
    client: anthropic.Anthropic,
    raw_jd: str,
    company: str,
    role: str,
    resume_for_assessment: str,
) -> dict[str, Any]:
    """Call `prompts/extract_and_assess.py` and validate the result against
    `ExtractAndAssessResult` before handing it back as a plain dict — a malformed
    response fails clearly here instead of a bare `KeyError` wherever
    `data["fit_score"]` etc. is read downstream."""
    raw = call_llm_json(
        client,
        system=extract_and_assess.SYSTEM,
        prompt=extract_and_assess.build(raw_jd, company, role, resume_for_assessment),
        max_tokens=4096,
    )
    try:
        return ExtractAndAssessResult.model_validate(raw).model_dump()
    except pydantic.ValidationError as e:
        raise LLMResponseError(
            f"The JD extractor returned data that didn't match the expected shape: {e}"
        ) from e


def _call_review_output(
    client: anthropic.Anthropic, tailored_md: str, jd_md: str, base_md: str
) -> dict[str, Any]:
    """Call `prompts/review_output.py` and validate the result against
    `TailoredResumeReview` before handing it back as a plain dict — shared by the
    initial step-4 review and every refinement round's re-review, so neither has
    to duplicate the validation."""
    raw = call_llm_json(
        client,
        system=review_output.SYSTEM,
        prompt=review_output.build(tailored_md, jd_md, base_md),
        max_tokens=4096,
    )
    try:
        return TailoredResumeReview.model_validate(raw).model_dump()
    except pydantic.ValidationError as e:
        raise LLMResponseError(
            f"The review step returned data that didn't match the expected shape: {e}"
        ) from e


def _call_with_page_limit(
    client: anthropic.Anthropic,
    build_prompt: Callable[[int], str],
    slug: str,
    output_dir: Path,
) -> str:
    """Call `build_prompt(trim_pass)` for a tailoring prompt, retrying with
    incrementing trim passes until the rendered PDF fits one page. Shared by both
    the initial tailor pass and each refinement round below, since both need the
    identical fits-one-page retry behavior — only what builds the prompt differs.
    """
    for trim_pass in range(settings.page_trim_attempts):
        tailored_md = call_llm_text(
            client,
            system=tailor_resume.SYSTEM,
            prompt=build_prompt(trim_pass),
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


def _tailor_with_page_limit(
    client: anthropic.Anthropic,
    base_md: str,
    jd_md: str,
    slug: str,
    output_dir: Path,
) -> str:
    """Tailor the resume from scratch, retrying with trim passes until it fits
    on one page."""
    return _call_with_page_limit(
        client,
        lambda trim_pass: tailor_resume.build(
            base_md,
            jd_md,
            trim_pass=trim_pass,
            always_include_title=settings.always_include_experience_title,
        ),
        slug,
        output_dir,
    )


def _refine_with_page_limit(
    client: anthropic.Anthropic,
    base_md: str,
    jd_md: str,
    remaining_gaps: list[str],
    improvement_suggestions: list[dict[str, Any]],
    slug: str,
    output_dir: Path,
) -> str:
    """One refinement round: re-tailor from the full base resume, folding in the
    previous round's review findings, retrying with trim passes the same way
    `_tailor_with_page_limit` does."""
    return _call_with_page_limit(
        client,
        lambda trim_pass: refine_resume.build(
            base_md,
            jd_md,
            remaining_gaps,
            improvement_suggestions,
            trim_pass=trim_pass,
            always_include_title=settings.always_include_experience_title,
        ),
        slug,
        output_dir,
    )


def _refine_until_no_improvement(
    client: anthropic.Anthropic,
    base_md: str,
    jd_md: str,
    jd: JobDescription,
    tailored_md: str,
    review: dict[str, Any],
    found: list[str],
    missing: list[str],
    slug: str,
    output_dir: Path,
) -> tuple[str, dict[str, Any], list[str], list[str], int]:
    """Repeatedly re-tailor using the previous round's own `remaining_gaps` and
    `improvement_suggestions` as feedback, accepting a round only if its reviewed
    fit_score strictly beats the best one found so far. Stops at the first round
    that fails to improve, when there's nothing left to act on, or after
    `settings.max_refine_attempts` rounds — whichever comes first, so this can't
    loop forever chasing marginal/noisy rewrites. Returns the best
    (tailored_md, review, found, missing) seen, plus how many rounds were accepted.
    """
    accepted = 0
    for attempt in range(settings.max_refine_attempts):
        remaining_gaps = review["remaining_gaps"]
        suggestions = review.get("improvement_suggestions", [])
        if not remaining_gaps and not suggestions:
            rprint("  Nothing left to act on — stopping refinement.")
            break

        rprint(f"[bold]Step 5:[/bold] Refining (round {attempt + 1})...")
        candidate_md = _refine_with_page_limit(
            client, base_md, jd_md, remaining_gaps, suggestions, slug, output_dir
        )
        candidate_review = _call_review_output(client, candidate_md, jd_md, base_md)

        if candidate_review["fit_score"] <= review["fit_score"]:
            rprint(
                f"  No improvement ({candidate_review['fit_score']} <= "
                f"{review['fit_score']}) — keeping previous round, stopping."
            )
            break

        rprint(f"  Improved: {review['fit_score']} → {candidate_review['fit_score']}")
        tailored_md, review = candidate_md, candidate_review
        found, missing = ats_keyword_coverage(tailored_md, jd.ats_keywords)
        accepted += 1

    return tailored_md, review, found, missing, accepted


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
        lines = []
        for b in bullets:
            supports = ", ".join(b["supports"]) if b["supports"] else "(none)"
            lines.append(f"- {b['bullet']} — supports: {supports}")
            lines.append(f"  - *Why:* {b['reason']}")
        return lines

    suggestions = review.get("improvement_suggestions", [])
    suggestion_lines = (
        [
            f"- {s['suggestion']}\n"
            f"  - *Evidence:* {s['evidence']}\n"
            f"  - *Addresses:* {s['addresses']}"
            for s in suggestions
        ]
        or ["None — nothing in the base resume would obviously improve this further."]
    )

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
        "## Suggestions to Improve Fit & ATS Coverage",
        "Grounded only in content already present somewhere in your base resume "
        "(an unused bullet variant, a skill demonstrated but not listed, etc.) — "
        "nothing here is invented.",
        *suggestion_lines,
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
