"""Post-tailoring review prompt: assesses the FINISHED tailored resume against the
JD — a holistic fit score plus a per-bullet relevance breakdown — so the user can
see how well the output actually lines up with the posting, and which bullets are
weak candidates to cut on a future manual pass. Unlike `assess_fit.py` (which gates
whether tailoring runs at all, on the *pre*-tailoring variant-free resume), this
runs unconditionally after export, on the resume as actually produced.

This step only reviews and annotates existing text — it never generates or edits
resume content, so the anti-fabrication rules that govern `tailor_resume.py` don't
apply to the TAILORED RESUME being reviewed. They do still apply, though, to
"improvement_suggestions" below: that section is also an LLM output, so it needs
its own anti-fabrication guard, grounded in the FULL base resume (every bullet
variant, every listed skill) rather than invented from the JD's wishlist — the
same standard `tailor_resume.py` enforces for the tailored output itself.

Called once from `pipelines/tailor.py` after PDF export.
"""

SYSTEM = (
    "You are an expert technical recruiter reviewing a finished, tailored resume "
    "against a job description. You are not generating or editing resume content — "
    "only assessing, annotating, and surfacing already-true content the candidate "
    "could choose to use differently. Never invent a skill, tool, or claim the "
    "candidate's base resume doesn't already support."
)


def build(tailored_md: str, jd_md: str, base_resume_md: str) -> str:
    return f"""Review this finished, tailored resume against the job description.

Return this exact JSON schema — no markdown fences:
{{
  "fit_score": float,        // 0.0 (no overlap) to 1.0 (excellent match)
  "reasoning": str,          // 1-2 sentence explanation of the score
  "remaining_gaps": [str],   // JD asks the resume still doesn't meet — empty if none
  "bullet_reviews": [
    {{
      "bullet": str,          // verbatim bullet text as it appears in the resume
                               // below, under Experience or Projects
      "supports": [str],      // JD requirements/keywords this bullet backs —
                               // empty list if it doesn't clearly support any
      "relevance": str,       // "high", "medium", or "low" — how much this bullet
                               // matters for this specific job. "low" marks a
                               // candidate to cut on a future edit.
      "reason": str           // 1 short sentence: why this relevance rating — name
                               // the specific JD requirement it does/doesn't match,
                               // not just a restatement of "relevance"
    }}
  ],
  "improvement_suggestions": [
    {{
      "suggestion": str,   // one concrete, actionable change — e.g. "swap this
                            // bullet's variant for the one mentioning Spark" or
                            // "add 'Kubernetes' to the Skills section"
      "evidence": str,     // the SPECIFIC existing content in the full base resume
                            // (below) that justifies this — a bullet variant not
                            // selected, a skill demonstrated in a bullet but absent
                            // from Skills, a project cut for space, etc. Quote or
                            // closely paraphrase it.
      "addresses": str     // the JD requirement, ATS keyword, or gap this would help
    }}
  ]
}}

Include one entry in "bullet_reviews" for every bullet under the Experience and
Projects sections of the TAILORED RESUME, in the order they appear.

For "improvement_suggestions": compare the TAILORED RESUME against the FULL BASE
RESUME below (which includes every bullet variant and the complete skills list,
not just what was selected this time) and the job description. Look for fit/ATS
improvements the candidate could make that are already TRUE of them — a more
JD-aligned variant of a bullet that wasn't picked, a skill demonstrated in a bullet
somewhere but missing from the Skills section, a project or experience entry cut
for space that would have closed a specific gap. Do NOT suggest anything not
already evidenced somewhere in the full base resume — if the JD wants something
genuinely absent, that belongs in "remaining_gaps", not here. Empty list if there's
nothing like this to surface.

Scoring guide for fit_score:
  0.0–0.3  Poor fit — core requirements are missing
  0.3–0.6  Partial fit — some overlap but significant gaps
  0.6–0.8  Good fit — most requirements met, minor gaps
  0.8–1.0  Strong fit — closely matches role requirements

TAILORED RESUME:
{tailored_md}

---
FULL BASE RESUME (all variants — for improvement_suggestions only; bullet_reviews
and fit_score are about the TAILORED RESUME above, not this):
{base_resume_md}

---
JOB DESCRIPTION:
{jd_md}"""
