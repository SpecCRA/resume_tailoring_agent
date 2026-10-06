"""The Resume <-> markdown round-trip: pure serialization, no LLM calls, used by
every pipeline that needs to read or write `resume_base.md` (or render a
variant-free view of it) — `pipelines/setup.py` (writes it), `pipelines/tailor.py`
(reads it for tailoring/refinement and the pre-tailor fit assessment), and
`pipelines/critique.py` (reads it for the integrity-auditor persona).

`resume_base.md` is both an LLM's output format and the only source of truth for
a `Resume` once a human starts hand-editing it, so `render_base_md`/`parse_base_md`
must stay exact inverses of each other. `render_originals_only_md` is a lighter
sibling used wherever only the underlying facts are needed, not every rephrasing
(fit assessment, skill suggestions, critique) — variants exist for bullet
*selection* at tailor time, not for judging what's true about the candidate.
"""

import re

from resume_agent.models.resume import (
    BulletPoint,
    EducationEntry,
    ExperienceEntry,
    ProjectEntry,
    Resume,
)


def render_base_md(resume: Resume) -> str:
    """Render resume to markdown, showing all bullet variants."""
    lines: list[str] = [f"# {resume.name}"]
    if resume.headline:
        lines.append(resume.headline)
    lines.append("")

    contact = " | ".join(
        filter(None, [resume.email, resume.phone, resume.linkedin, resume.github, resume.location])
    )
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


def render_originals_only_md(resume: Resume) -> str:
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


def parse_base_md(md_text: str) -> Resume:
    """Parse a base_resume.md — as produced by render_base_md, including any
    manual edits made on top of it — back into a Resume. Inverse of render_base_md."""
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
