"""One-time (and re-run-on-edit) pipeline: turns a resume PDF into `resume_base.md`.

`run_setup` parses a PDF into a `Resume`, backfills 3-5 phrasing variants per
bullet, and writes the base resume plus a sibling adjacent-skills suggestions
file. `run_review_base` re-parses an existing (possibly hand-edited)
`resume_base.md` and backfills variants only for bullets that don't have them yet,
leaving everything else untouched — this is what makes the base resume safe to
edit directly rather than only through the LLM.

The other half of this module is the markdown render/parse round-trip
(`_render_base_md` / `_parse_base_md`) that makes that hand-editing possible:
`resume_base.md` is both the LLM's output format and the only source of truth for
a `Resume`, so the two functions must stay exact inverses of each other.
`_render_originals_only_md` is a lighter sibling used wherever only the
underlying facts are needed, not every rephrasing (fit assessment, skill
suggestions) — variants exist for bullet *selection*, not judgment.
"""

import re
from pathlib import Path

import anthropic
import pydantic
from rich import print as rprint

from resume_agent.config import settings
from resume_agent.errors import LLMResponseError
from resume_agent.models.resume import (
    BulletPoint,
    EducationEntry,
    ExperienceEntry,
    ProjectEntry,
    Resume,
)
from resume_agent.prompts import parse_resume, rewrite_bullets, suggest_adjacent_skills
from resume_agent.tools.llm import call_llm_json
from resume_agent.tools.pdf_reader import extract_text


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
    base_path.write_text(_render_base_md(resume))
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
    resume = _parse_base_md(base_path.read_text())

    rprint("[bold]Step 2:[/bold] Backfilling variants for new/edited bullets...")
    _generate_all_bullet_variants(client, resume)

    rprint("[bold]Step 3:[/bold] Rewriting base resume template...")
    base_path.write_text(_render_base_md(resume))
    _write_skill_suggestions(client, resume, base_path)
    rprint(f"[green]Done! Base resume refreshed:[/green] {base_path}")
    return base_path


def _generate_all_bullet_variants(client: anthropic.Anthropic, resume: Resume) -> None:
    """Backfill bullet variants for every experience/project bullet that lacks them."""
    for exp in resume.experience:
        ctx = f"{exp.title} at {exp.company}"
        exp.bullets = _ensure_bullet_variants(
            client, exp.bullets, ctx, settings.max_bullet_variants
        )

    for proj in resume.projects:
        ctx = f"Project: {proj.name}"
        proj.bullets = _ensure_bullet_variants(
            client, proj.bullets, ctx, settings.max_project_bullet_variants
        )


def _ensure_bullet_variants(
    client: anthropic.Anthropic, bullets: list[BulletPoint], context: str, n: int
) -> list[BulletPoint]:
    """Generate variants only for bullets that don't already have them."""
    result: list[BulletPoint] = []
    for bullet in bullets:
        if bullet.variants:
            result.append(bullet)
            continue
        variants = call_llm_json(
            client,
            system=rewrite_bullets.SYSTEM,
            prompt=rewrite_bullets.build(bullet.original, context, n),
            max_tokens=2048,
        )
        result.append(BulletPoint(original=bullet.original, variants=variants))
    return result


def _write_skill_suggestions(client: anthropic.Anthropic, resume: Resume, base_path: Path) -> None:
    """Suggest adjacent skills for a human to review, written to a sibling file that
    the tailoring pipeline never reads. Nothing here is used until a human manually
    promotes an entry into the resume's own `## Skills` line."""
    suggestions_path = base_path.with_name(f"{base_path.stem}.suggestions.md")
    result = call_llm_json(
        client,
        system=suggest_adjacent_skills.SYSTEM,
        prompt=suggest_adjacent_skills.build(_render_originals_only_md(resume)),
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


def _render_base_md(resume: Resume) -> str:
    """Render resume to markdown, showing all bullet variants."""
    lines: list[str] = [f"# {resume.name}"]
    if resume.headline:
        lines.append(resume.headline)
    lines.append("")

    contact = " | ".join(filter(None, [resume.email, resume.phone, resume.linkedin, resume.github, resume.location]))
    lines += [contact, ""]

    if resume.summary:
        lines += ["## Summary", resume.summary, ""]

    lines += ["## Skills", ", ".join(resume.skills), ""]

    lines += ["## Experience"]
    for exp in resume.experience:
        loc = f" — {exp.location}" if exp.location else ""
        lines += [f"### {exp.title} | {exp.company}{loc}", f"*{exp.dates}*", ""]
        for bp in exp.bullets:
            lines += [f"- {bp.original}"]
            for i, v in enumerate(bp.variants, 1):
                lines += [f"  - v{i}: {v}"]
        lines.append("")

    lines += ["## Education"]
    for edu in resume.education:
        gpa = f" | GPA: {edu.gpa}" if edu.gpa else ""
        lines += [f"### {edu.degree} | {edu.institution}", f"*{edu.dates}{gpa}*", ""]

    lines += ["## Projects"]
    for proj in resume.projects:
        url = f" ([link]({proj.url}))" if proj.url else ""
        lines += [f"### {proj.name}{url}"]
        if proj.description:
            lines += [proj.description]
        for bp in proj.bullets:
            lines += [f"- {bp.original}"]
            for i, v in enumerate(bp.variants, 1):
                lines += [f"  - v{i}: {v}"]
        lines.append("")

    return "\n".join(lines)


def _render_originals_only_md(resume: Resume) -> str:
    """Render resume to markdown with each bullet's original wording only —
    no variant rephrasings. All variants preserve the same underlying
    accomplishment, so they're pure redundancy for anything that only needs
    to judge overall fit rather than pick a specific wording."""
    lines: list[str] = [f"# {resume.name}"]
    if resume.headline:
        lines.append(resume.headline)
    lines.append("")

    if resume.summary:
        lines += ["## Summary", resume.summary, ""]

    lines += ["## Skills", ", ".join(resume.skills), ""]

    lines += ["## Experience"]
    for exp in resume.experience:
        loc = f" — {exp.location}" if exp.location else ""
        lines += [f"### {exp.title} | {exp.company}{loc}", f"*{exp.dates}*", ""]
        for bp in exp.bullets:
            lines += [f"- {bp.original}"]
        lines.append("")

    lines += ["## Education"]
    for edu in resume.education:
        gpa = f" | GPA: {edu.gpa}" if edu.gpa else ""
        lines += [f"### {edu.degree} | {edu.institution}", f"*{edu.dates}{gpa}*", ""]

    lines += ["## Projects"]
    for proj in resume.projects:
        lines += [f"### {proj.name}"]
        if proj.description:
            lines += [proj.description]
        for bp in proj.bullets:
            lines += [f"- {bp.original}"]
        lines.append("")

    return "\n".join(lines)


def _parse_base_md(md_text: str) -> Resume:
    """Parse a base_resume.md — as produced by _render_base_md, including any
    manual edits made on top of it — back into a Resume. Inverse of _render_base_md."""
    preamble, sections = _split_top_sections(md_text.splitlines())

    preamble_content = [line for line in preamble if line.strip()]
    name = preamble_content[0].lstrip("#").strip()
    default_contact = {"email": "", "phone": "", "linkedin": "", "github": "", "location": ""}
    if len(preamble_content) >= 3:
        # name, headline, contact
        headline: str | None = preamble_content[1]
        contact = _parse_contact_line(preamble_content[2])
    elif len(preamble_content) == 2:
        # name, contact — no headline
        headline = None
        contact = _parse_contact_line(preamble_content[1])
    else:
        headline = None
        contact = default_contact

    summary_lines = [line for line in sections.get("Summary", []) if line.strip()]
    summary = "\n".join(summary_lines) if summary_lines else None

    skills_lines = [line for line in sections.get("Skills", []) if line.strip()]
    skills = [s.strip() for s in skills_lines[0].split(",")] if skills_lines else []

    experience: list[ExperienceEntry] = []
    for entry_lines in _split_entries(sections.get("Experience", [])):
        header = entry_lines[0][len("### "):].strip()
        title, _, company_part = header.partition(" | ")
        company, _, location = company_part.partition(" — ")
        dates = _find_dates_line(entry_lines[1:])
        experience.append(ExperienceEntry(
            company=company.strip(),
            title=title.strip(),
            dates=dates,
            location=location.strip() or None,
            bullets=_parse_bullets(entry_lines[1:]),
        ))

    education: list[EducationEntry] = []
    for entry_lines in _split_entries(sections.get("Education", [])):
        header = entry_lines[0][len("### "):].strip()
        degree, _, institution = header.partition(" | ")
        meta = _find_dates_line(entry_lines[1:])
        dates, _, gpa_part = meta.partition(" | GPA: ")
        education.append(EducationEntry(
            institution=institution.strip(),
            degree=degree.strip(),
            dates=dates.strip(),
            gpa=float(gpa_part) if gpa_part else None,
        ))

    projects: list[ProjectEntry] = []
    for entry_lines in _split_entries(sections.get("Projects", [])):
        header = entry_lines[0][len("### "):].strip()
        if " ([link](" in header and header.endswith(")"):
            proj_name, _, link_part = header.partition(" ([link](")
            url = link_part[:-2]  # strip trailing "))"
        else:
            proj_name, url = header, None
        rest = entry_lines[1:]
        desc_lines = [
            line for line in rest
            if line.strip() and not line.startswith("- ") and not line.startswith("  - v")
        ]
        projects.append(ProjectEntry(
            name=proj_name.strip(),
            description=desc_lines[0].strip() if desc_lines else None,
            bullets=_parse_bullets(rest),
            url=url,
        ))

    return Resume(
        name=name,
        email=contact["email"] or "",
        phone=contact["phone"] or "",
        linkedin=contact["linkedin"],
        github=contact["github"],
        location=contact["location"],
        headline=headline,
        summary=summary,
        skills=skills,
        experience=experience,
        education=education,
        projects=projects,
    )


def _split_top_sections(lines: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    """Split lines into the preamble (before the first '## ') and a dict of
    '## Section' name -> body lines."""
    preamble: list[str] = []
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        if line.startswith("## "):
            current = line[len("## "):].strip()
            sections[current] = []
        elif current is None:
            preamble.append(line)
        else:
            sections[current].append(line)
    return preamble, sections


def _split_entries(body_lines: list[str]) -> list[list[str]]:
    """Split a section body into one line-group per '### ' entry."""
    entries: list[list[str]] = []
    current: list[str] | None = None
    for line in body_lines:
        if line.startswith("### "):
            current = [line]
            entries.append(current)
        elif current is not None:
            current.append(line)
    return entries


def _parse_bullets(lines: list[str]) -> list[BulletPoint]:
    bullets: list[BulletPoint] = []
    for line in lines:
        if line.startswith("- "):
            bullets.append(BulletPoint(original=line[2:].strip()))
        elif line.startswith("  - v") and bullets:
            bullets[-1].variants.append(re.sub(r"^  - v\d+:\s*", "", line))
    return bullets


def _find_dates_line(lines: list[str]) -> str:
    """Find the '*...*' metadata line within an entry and strip the asterisks."""
    line = next((ln for ln in lines if ln.strip().startswith("*")), "")
    return line.strip().strip("*")


def _parse_contact_line(line: str) -> dict[str, str]:
    parts = [p.strip() for p in line.split("|")]
    email = parts[0] if len(parts) > 0 else ""
    phone = parts[1] if len(parts) > 1 else ""
    linkedin = github = location = ""
    for extra in parts[2:]:
        low = extra.lower()
        if "linkedin" in low:
            linkedin = extra
        elif "github" in low:
            github = extra
        else:
            location = extra
    return {
        "email": email,
        "phone": phone,
        "linkedin": linkedin,
        "github": github,
        "location": location,
    }