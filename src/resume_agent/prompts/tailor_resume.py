SYSTEM = (
    "You are an expert resume coach. Select and tailor resume content "
    "to maximize ATS score and recruiter relevance for a specific job. "
    "Never invent skills, experience, tools, metrics, or claims that are not "
    "already present in the candidate's resume, even if the job description "
    "asks for them — omission is always preferable to fabrication."
)


def build(resume_md: str, jd_md: str, fit_score: float, trim_pass: int = 0) -> str:
    trim_note = (
        f"\n\nIMPORTANT: This is trim pass {trim_pass}. The previous output exceeded one page. "
        "Remove the least-relevant bullets/experience entries and shorten descriptions "
        "until it fits on one page. Do not remove or shorten the header (name + contact) "
        "or the Education section."
        if trim_pass > 0
        else ""
    )
    return f"""Tailor the resume below for the job description provided.

Rules:
1. Assess the job description first, then select only the experience entries,
    projects, and skills that are most relevant to it. Omit experience or project
    entries with zero relevance to the role. Select at most 2 projects — the ones
    most relevant to the job description — and shorten the Experience section
    (fewer bullets per entry, or omitting the least-relevant experience entries) as
    needed to make room for them.
2. For each remaining bullet, default to the ORIGINAL wording. Only replace it with
    one of the listed variants (v1, v2, ...) if the original does not fit the job
    description well and a variant is a clearly closer fit. Do not swap wording just
    for style or variety — reword only the bullets that need it.
3. Reorder skills to front-load keywords from the job description.
4. Keep the summary focused on the exact role and company.
5. Output ATS-safe markdown: no tables, no columns, plain section headers.
6. Format: # Name, contact line, ## Summary, ## Skills, ## Experience, ## Education,
    ## Projects (at most 2 entries). The header (name + contact line) and the
    Education section must always be included in full — never omit them, regardless
    of relevance to the job description.
7. Fit score context: {fit_score:.0%} match — {'prioritize best fit' if fit_score > 0.7 else 'note skills gaps clearly in summary'}.
8. Do not add any skill, tool, technology, responsibility, or achievement that is not
    already stated in the resume below, even if it appears in the job description.
    Reordering, rewording, and emphasis are fine; new claims are not. If there is a
    genuine gap between the resume and the JD, leave it as a gap rather than papering
    over it.
{trim_note}

---
RESUME (all variants):
{resume_md}

---
JOB DESCRIPTION:
{jd_md}

Output ONLY the tailored markdown resume."""
