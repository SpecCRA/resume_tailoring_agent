import json
from pathlib import Path

import anthropic
from rich import print as rprint

from resume_agent.config import settings
from resume_agent.models.resume import BulletPoint, ExperienceEntry, ProjectEntry, Resume
from resume_agent.tools.pdf_reader import extract_text
from resume_agent.prompts import parse_resume, rewrite_bullets


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
    msg = client.messages.create(
        model=settings.claude_model,
        max_tokens=4096,
        system=parse_resume.SYSTEM,
        messages=[{"role": "user", "content": parse_resume.build(raw_text)}],
    )
    data = json.loads(msg.content[0].text)
    resume = Resume.model_validate(data)

    # ── Rewrite bullets ──
    rprint("[bold]Step 3:[/bold] Rewriting bullets with variants...")
    for exp in resume.experience:
        ctx = f"{exp.title} at {exp.company}"
        bullets: list[BulletPoint] = []
        for bullet_text in [b.original for b in exp.bullets]:
            msg = client.messages.create(
                model=settings.claude_model,
                max_tokens=1024,
                system=rewrite_bullets.SYSTEM,
                messages=[{"role": "user", "content": rewrite_bullets.build(
                    bullet_text, ctx, settings.max_bullet_variants
                )}],
            )
            variants = json.loads(msg.content[0].text)
            bullets.append(BulletPoint(original=bullet_text, variants=variants))
        exp.bullets = bullets

    for proj in resume.projects:
        ctx = f"Project: {proj.name}"
        bullets = []
        for bullet_text in [b.original for b in proj.bullets]:
            msg = client.messages.create(
                model=settings.claude_model,
                max_tokens=512,
                system=rewrite_bullets.SYSTEM,
                messages=[{"role": "user", "content": rewrite_bullets.build(
                    bullet_text, ctx, 3
                )}],
            )
            variants = json.loads(msg.content[0].text)
            bullets.append(BulletPoint(original=bullet_text, variants=variants))
        proj.bullets = bullets

    # ── Write base resume ──
    rprint("[bold]Step 4:[/bold] Writing base resume template...")
    base_path = Path(settings.base_resume_path)
    base_path.parent.mkdir(parents=True, exist_ok=True)
    base_path.write_text(_render_base_md(resume))
    rprint(f"[green]Done! Base resume written to:[/green] {base_path}")
    return base_path


def _render_base_md(resume: Resume) -> str:
    """Render resume to markdown, showing all bullet variants."""
    lines: list[str] = [f"# {resume.name}", ""]

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