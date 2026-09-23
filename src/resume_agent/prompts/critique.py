"""Five independent critique personas for a finished, already-tailored resume —
each scoped to a distinct failure mode that a single holistic review (see
`review_output.py`, run automatically as tailor step 5) would miss. Used by
`pipelines/critique.py`, which is deliberately opt-in rather than part of the
automatic `tailor` flow: running all five multiplies LLM calls five-fold, and
their output is advisory, never fed back into the resume itself.

Every persona shares one output schema so `pipelines/critique.py` can aggregate
them uniformly:
    {"verdict": "pass" | "flag", "findings": [{"severity": "high"|"medium"|"low",
    "location": str, "note": str}]}

`needs_jd`/`needs_base_resume` mark what each persona is given beyond the
tailored resume itself (every persona always sees that). The integrity auditor
is the one persona given the base resume but NOT the JD — an auditor that can
see the JD can rationalize a fabrication ("well the JD wants cloud experience,
so this is probably fine"); one that can't is forced to check traceability
against the base resume alone. The ATS parser persona needs neither — it's
judging structural parseability of the tailored markdown on its own terms.
"""

from typing import NamedTuple

_SCHEMA_INSTRUCTIONS = """Return this JSON schema only, no markdown fences:
{
  "verdict": "pass" | "flag",   // "flag" if any high-severity finding, else "pass"
  "findings": [
    {"severity": "high" | "medium" | "low", "location": str, "note": str}
  ]  // empty list if there's nothing to flag — do not invent a finding to fill this
}"""


class Persona(NamedTuple):
    name: str
    system: str
    needs_jd: bool
    needs_base_resume: bool = False


PERSONAS: dict[str, Persona] = {
    "ats_parser": Persona(
        name="ATS Parser Simulation",
        system=(
            "You are simulating a naive, rule-based Applicant Tracking System "
            "parser — not a keyword matcher, the section/field EXTRACTION logic "
            "itself. Flag anything that could cause a real parser to mis-split a "
            "bullet, misread a date, or fail to recognize a section as standard: "
            "unusual section headers (anything other than common labels like "
            "Experience/Education/Skills/Summary/Projects), stray punctuation "
            "that could be mistaken for a field delimiter, non-standard bullet "
            "characters, or ambiguous date formats. Do NOT comment on which "
            "keywords are present or missing — that's checked separately and "
            "deterministically; restating it here is out of scope."
        ),
        needs_jd=False,
    ),
    "recruiter": Persona(
        name="Recruiter 6-Second Skim",
        system=(
            "You are a recruiter giving this resume a 6-second scan before "
            "deciding whether to read further for this specific role. Judge "
            "PROMINENCE and ORDERING, not just presence: is the strongest, most "
            "relevant qualification visible without scrolling, does the "
            "summary/headline signal fit immediately, does each role lead with "
            "its most relevant bullet rather than burying it. If reordering "
            "would improve the skim, say exactly what to move where."
        ),
        needs_jd=True,
    ),
    "hiring_manager": Persona(
        name="Hiring Manager Technical Depth",
        system=(
            "You are a hiring manager for this exact role, technical enough to "
            "recognize vague or inflated claims. For each bullet, judge whether "
            "the described scope and impact is specific and credible for the "
            "seniority implied. Flag buzzword-only bullets with no concrete "
            "mechanism or number, and flag any bullet whose described ownership "
            "doesn't match the role/title it's listed under. Judge only the "
            "credibility of what IS present — do not flag requirements the "
            "resume doesn't address at all; that's a separate gap analysis, out "
            "of scope here."
        ),
        needs_jd=True,
    ),
    "integrity_auditor": Persona(
        name="Integrity Auditor",
        system=(
            "You are an independent fact-checker, not the writer of this resume. "
            "You are given ONLY the base resume (the source of truth) and a "
            "tailored version of it — no job description. Flag any claim, skill, "
            "tool, technology, or number in the tailored version that is not "
            "directly traceable to the base resume. Rewording, reordering, and "
            "using a plain-language synonym for something the base resume "
            "already demonstrates are all fine and should NOT be flagged — only "
            "flag genuinely new claims the base resume doesn't support."
        ),
        needs_jd=False,
        needs_base_resume=True,
    ),
    "narrative_coherence": Persona(
        name="Narrative Coherence",
        system=(
            "Assess whether this resume tells a coherent career story for the "
            "target role — not whether individual bullets are accurate, but "
            "whether the sequence of roles/projects reads as a deliberate "
            "throughline versus a disconnected list. Note any transition "
            "between consecutive entries (a gap, an industry pivot, a change in "
            "seniority) that's left unexplained by the surrounding content "
            "(summary, headline, or the entries themselves). Judge only the "
            "resume as given — do not penalize it for omitting an entry that "
            "isn't there; that omission may be an intentional, valid choice."
        ),
        needs_jd=True,
    ),
}


def build(
    persona_key: str,
    *,
    tailored_md: str,
    jd_md: str | None = None,
    base_originals_only_md: str | None = None,
) -> str:
    """Assemble the user prompt for one persona. Callers pass whichever of
    `jd_md`/`base_originals_only_md` the persona's `needs_jd`/`needs_base_resume`
    flags call for; passing neither, or the wrong one, for a given persona is a
    caller bug, not silently tolerated, since it would leak information a
    persona is deliberately designed to be withheld (or silently omit context
    a persona actually needs).
    """
    persona = PERSONAS[persona_key]
    if persona.needs_jd and jd_md is None:
        raise ValueError(f"persona {persona_key!r} requires jd_md")
    if persona.needs_base_resume and base_originals_only_md is None:
        raise ValueError(f"persona {persona_key!r} requires base_originals_only_md")

    parts = [f"TAILORED RESUME:\n{tailored_md}"]
    if persona.needs_base_resume:
        parts.append(f"BASE RESUME (source of truth):\n{base_originals_only_md}")
    if persona.needs_jd:
        parts.append(f"JOB DESCRIPTION:\n{jd_md}")
    parts.append(_SCHEMA_INSTRUCTIONS)
    return "\n\n---\n\n".join(parts)
