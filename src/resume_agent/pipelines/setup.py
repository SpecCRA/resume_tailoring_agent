"""One-time (and re-run-on-edit) pipeline: turns a resume PDF into `resume_base.md`.

`run_setup` parses a PDF into a `Resume`, backfills 3-5 phrasing variants per
bullet, and writes the base resume plus a sibling adjacent-skills suggestions
file. `run_review_base` re-parses an existing (possibly hand-edited)
`resume_base.md` and backfills variants only for bullets that don't have them yet,
leaving everything else untouched — this is what makes the base resume safe to
edit directly rather than only through the LLM.

The markdown render/parse round-trip itself (`render_base_md`/`parse_base_md`/
`render_originals_only_md`) lives in `tools/resume_markdown.py`, not here — it's
pure serialization with no LLM calls, and `pipelines/tailor.py`/`pipelines/
critique.py` need it too, so it has its own module rather than being two other
pipelines' private import of this one.
"""

from pathlib import Path
from typing import Any

import anthropic
import pydantic
from rich import print as rprint

from resume_agent.config import settings
from resume_agent.errors import LLMResponseError
from resume_agent.models.resume import BulletPoint, Resume
from resume_agent.prompts import parse_resume, rewrite_bullets, suggest_adjacent_skills
from resume_agent.tools.llm import call_llm_json
from resume_agent.tools.pdf_reader import extract_text
from resume_agent.tools.resume_markdown import (
    parse_base_md,
    render_base_md,
    render_originals_only_md,
)


def run_setup(pdf_path: str) -> Path:
    """
    One-time pipeline: PDF resume → base/resume_base.md with all bullet variants.
    Returns the path to the generated base resume.
    """
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    rprint("[bold]Step 1:[/bold] Extracting text from PDF...")
    raw_text = extract_text(pdf_path)

    # ── Parse sections ──
    rprint("[bold]Step 2:[/bold] Parsing and tagging resume sections...")
    data = call_llm_json(
        client, system=parse_resume.SYSTEM, prompt=parse_resume.build(raw_text), max_tokens=4096
    )
    try:
        resume = Resume.model_validate(data)
    except pydantic.ValidationError as e:
        raise LLMResponseError(
            f"The resume parser returned data that didn't match the expected shape: {e}"
        ) from e

    # ── Rewrite bullets ──
    rprint("[bold]Step 3:[/bold] Rewriting bullets with variants...")
    _generate_all_bullet_variants(client, resume)

    # ── Write base resume ──
    rprint("[bold]Step 4:[/bold] Writing base resume template...")
    base_path = Path(settings.base_resume_path)
    base_path.parent.mkdir(parents=True, exist_ok=True)
    base_path.write_text(render_base_md(resume))
    _write_skill_suggestions(client, resume, base_path)
    rprint(f"[green]Done! Base resume written to:[/green] {base_path}")
    return base_path


def run_review_base() -> Path:
    """
    Re-review pipeline: re-parse an existing (possibly hand-edited) base_resume.md
    and backfill bullet variants for anything new, leaving already-reviewed
    bullets untouched.
    """
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    base_path = Path(settings.base_resume_path)

    rprint("[bold]Step 1:[/bold] Parsing existing base resume markdown...")
    resume = parse_base_md(base_path.read_text())

    rprint("[bold]Step 2:[/bold] Backfilling variants for new/edited bullets...")
    _generate_all_bullet_variants(client, resume)

    rprint("[bold]Step 3:[/bold] Rewriting base resume template...")
    base_path.write_text(render_base_md(resume))
    _write_skill_suggestions(client, resume, base_path)
    rprint(f"[green]Done! Base resume refreshed:[/green] {base_path}")
    return base_path


def _generate_all_bullet_variants(client: anthropic.Anthropic, resume: Resume) -> None:
    """Backfill bullet variants for every experience/project bullet that lacks them,
    in a single batched call rather than one call per bullet."""
    items: list[dict[str, Any]] = []
    targets: list[BulletPoint] = []

    def _collect(
        bullets: list[BulletPoint], context: str, n: int, is_most_recent: bool = False
    ) -> None:
        for bullet in bullets:
            if bullet.variants:
                continue
            items.append({
                "id": len(items),
                "bullet": bullet.original,
                "context": context,
                "n": n,
                "is_most_recent": is_most_recent,
            })
            targets.append(bullet)

    # The first Experience entry is the candidate's most recent role (resumes
    # are conventionally reverse-chronological, and render_base_md/parse_base_md
    # preserve whatever order the base resume lists them in) — flagged so
    # rewrite_bullets.py can allow that entry's variants to run longer, since
    # it's the role a reader will weight most heavily.
    for i, exp in enumerate(resume.experience):
        _collect(
            exp.bullets,
            f"{exp.title} at {exp.company}",
            settings.max_bullet_variants,
            is_most_recent=(i == 0),
        )
    for proj in resume.projects:
        _collect(proj.bullets, f"Project: {proj.name}", settings.max_project_bullet_variants)

    if not items:
        return

    result = call_llm_json(
        client,
        system=rewrite_bullets.SYSTEM,
        prompt=rewrite_bullets.build(items),
        max_tokens=1024 + 300 * len(items),
    )
    by_id = {b["id"]: b["variants"] for b in result["bullets"]}
    missing = [item["id"] for item in items if item["id"] not in by_id]
    if missing:
        raise LLMResponseError(
            f"Bullet-variant response was missing variants for id(s) {missing} "
            f"out of {len(items)} requested."
        )
    for item, bullet in zip(items, targets):
        bullet.variants = by_id[item["id"]]


def _write_skill_suggestions(client: anthropic.Anthropic, resume: Resume, base_path: Path) -> None:
    """Suggest adjacent skills for a human to review, written to a sibling file that
    the tailoring pipeline never reads. Nothing here is used until a human manually
    promotes an entry into the resume's own `## Skills` line."""
    suggestions_path = base_path.with_name(f"{base_path.stem}.suggestions.md")
    result = call_llm_json(
        client,
        system=suggest_adjacent_skills.SYSTEM,
        prompt=suggest_adjacent_skills.build(render_originals_only_md(resume)),
        max_tokens=1024,
    )
    suggestions = result.get("suggestions", [])
    if not suggestions:
        suggestions_path.unlink(missing_ok=True)
        return
    lines = [
        "# Suggested Skills — review before use",
        "",
        "These are not part of your resume yet. Review each one, then manually move",
        "anything accurate into the `## Skills` line of your base resume. The tailoring",
        "pipeline never reads this file.",
        "",
        *[f"- {s['skill']} — {s['evidence']}" for s in suggestions],
    ]
    suggestions_path.write_text("\n".join(lines))
