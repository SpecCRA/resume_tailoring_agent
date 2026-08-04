"""The core per-job tailoring prompt — the last, most expensive LLM call in the
pipeline, only reached after the fit assessment recommends applying.

Given the full base resume (every bullet variant) and the structured JD, it
selects the most relevant experience/projects/skills, picks between pre-generated
bullet variants (never rewriting on the fly), mirrors the JD's own vocabulary,
and enforces ATS-safe single-column markdown — all subordinate to the final rule:
never add a skill, tool, or claim that isn't already stated in the resume, even
if the JD asks for it. Called in a retry loop by `pipelines/tailor.py.
_tailor_with_page_limit`, which re-invokes it with `trim_pass` incremented until
the rendered PDF fits on one page.

Gaps between the resume and the JD are never surfaced in the resume itself — a
candidate-facing document is the wrong place to advertise what's missing. They're
left as silent omissions here and reported separately in the assessment file
written by `pipelines/tailor.py._render_assessment_md`.
"""

SYSTEM = (
    "You are an expert resume coach. Select and tailor resume content "
    "to maximize ATS score and recruiter relevance for a specific job. "
    "Never invent skills, experience, tools, metrics, or claims that are not "
    "already present in the candidate's resume, even if the job description "
    "asks for them — omission is always preferable to fabrication."
)


def build(resume_md: str, jd_md: str, trim_pass: int = 0) -> str:
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
    entries with zero relevance to the role, and cut any skills that are irrelevant
    to this specific posting — a long undifferentiated skills list reads as
    unfocused. Select at most 2 projects — the ones most relevant to the job
    description — and shorten the Experience section (fewer bullets per entry, or
    omitting the least-relevant experience entries) as needed to make room for them.
2. For each remaining bullet, default to the ORIGINAL wording. Only replace it with
    one of the variants (v1, v2, ...) listed directly beneath THAT SAME bullet if the
    original does not fit the job description well and a variant is a clearly closer
    fit. Do not swap wording just for style or variety — reword only the bullets that
    need it. When more than one variant would be a valid swap, prefer whichever
    variant's existing framing matches the kind of impact the job description
    emphasizes (e.g. a throughput/latency/scale framing for a job emphasizing
    large-scale systems, a stakeholder/adoption framing for a job emphasizing business
    impact) — still only ever selecting among that bullet's own variants, never a
    variant listed under a different bullet and never inventing a new one. Bullets
    within a role or project have no obligation to stay in their original order — lead
    with whichever existing bullet is most relevant to this job — but every bullet you
    output must stay under the same experience or project entry it appears under in
    the source resume below.
3. Reorder skills to front-load keywords from the job description.
4. Mirror the job description's own vocabulary where it names, with a different
    term, something the resume already demonstrates (e.g. resume says "ETL
    pipelines", job description says "batch and streaming" — use their term if it's
    a genuine description of the same work). This is relabeling something already
    true, not a new claim — never use the job description's term for a skill or tool
    the resume does not actually support (see rule 10).
5. Keep the summary focused on the exact role and company.
6. If the resume has a headline line under the name, and the posted job title is a
    defensible match for the candidate's actual experience and skills, update the
    headline to the posted title, keeping it on its own line directly beneath the
    name — never merge it into the contact line. Otherwise keep the candidate's own
    existing headline as-is. Never invent a headline if the resume doesn't have one —
    a candidate with no headline line in the source resume stays headline-less; do
    not borrow a title from the job description, the posted role, or any experience
    entry below to manufacture one. Each experience entry below keeps its own
    original title exactly as given, regardless of what headline (if any) is used —
    different entries are expected to show different titles from each other and from
    the headline, and none should be rewritten to match another entry, the headline,
    or the posted role.
7. The first time a well-known, unambiguous acronym that already appears in the
    source resume shows up in your output, spell it out once, e.g. "Extract,
    Transform, Load (ETL)". Skip this for any acronym whose expansion isn't
    obvious/unambiguous — guessing wrong is itself a fabrication.
8. Output ATS-safe markdown: no tables, no columns, plain section headers.
9. Format: # Name, optional headline line, contact line, ## Summary, ## Skills,
    ## Experience, ## Education, ## Projects (at most 2 entries). The header (name +
    optional headline + contact line) and the Education section must always be
    included in full — never omit them, regardless of relevance to the job
    description. The contact line holds only contact details (email, phone,
    LinkedIn, GitHub, location) — never a job title or headline text.
10. Do not add any skill, tool, technology, responsibility, or achievement that is
    not already stated in the resume below, even if it appears in the job
    description. Reordering, rewording, relabeling with the job description's own
    terms (rule 4), and emphasis are fine; new claims are not. If there is a genuine
    gap between the resume and the JD, leave it as a silent omission — do not call
    it out anywhere in the resume (including the summary).
11. Never move a bullet, or one of its variants, to a different experience or
    project entry than the one it's listed under in the source resume — not even
    between two entries that share the same job title (e.g. two different "Data
    Scientist" roles at different companies below are still distinct entries; a
    bullet that belongs to one must never appear under the other). Before finalizing
    your output, double check every bullet you kept is still under its original
    company/project entry.
{trim_note}

---
RESUME (all variants):
{resume_md}

---
JOB DESCRIPTION:
{jd_md}

Output ONLY the tailored markdown resume."""
