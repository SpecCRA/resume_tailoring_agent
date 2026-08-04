"""Post-tailoring review prompt: assesses the FINISHED tailored resume against the
JD — a holistic fit score plus a per-bullet relevance breakdown — so the user can
see how well the output actually lines up with the posting, and which bullets are
weak candidates to cut on a future manual pass. Unlike `assess_fit.py` (which gates
whether tailoring runs at all, on the *pre*-tailoring variant-free resume), this
runs unconditionally after export, on the resume as actually produced.

This step only reviews and annotates existing text — it never generates or edits
resume content, so the anti-fabrication rules that govern `tailor_resume.py` don't
apply here. Called once from `pipelines/tailor.py` after PDF export.
"""

SYSTEM = (
    "You are an expert technical recruiter reviewing a finished, tailored resume "
    "against a job description. You are not generating or editing resume content — "
    "only assessing and annotating what's already there."
)


def build(tailored_md: str, jd_md: str) -> str:
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
      "relevance": str        // "high", "medium", or "low" — how much this bullet
                               // matters for this specific job. "low" marks a
                               // candidate to cut on a future edit.
    }}
  ]
}}

Include one entry in "bullet_reviews" for every bullet under the Experience and
Projects sections, in the order they appear.

Scoring guide for fit_score:
  0.0–0.3  Poor fit — core requirements are missing
  0.3–0.6  Partial fit — some overlap but significant gaps
  0.6–0.8  Good fit — most requirements met, minor gaps
  0.8–1.0  Strong fit — closely matches role requirements

TAILORED RESUME:
{tailored_md}

---
JOB DESCRIPTION:
{jd_md}"""
