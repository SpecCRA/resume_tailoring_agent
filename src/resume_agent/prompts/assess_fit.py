"""Fit-assessment prompt: scores the base resume against a JD, returning a
0.0-1.0 fit_score, a short reasoning string, and any concrete gaps. Used by
`pipelines/tailor.py` as a gate — below `settings.min_fit_score`, the pipeline
stops before the more expensive tailoring call runs at all. Deliberately takes a
variant-free resume view (see `_render_originals_only_md`) since judging overall
fit doesn't need 3-5 rephrasings of the same bullet.
"""

SYSTEM = (
    "You are an expert technical recruiter. Assess how well a candidate's resume "
    "matches a job description and return only valid JSON."
)


def build(resume_md: str, jd_md: str) -> str:
    return f"""Assess how well this resume matches the job description.

Return this exact JSON schema — no markdown fences:
{{
  "fit_score": float,   // 0.0 (no overlap) to 1.0 (excellent match)
  "reasoning": str,     // 1-2 sentence explanation of the score
  "gaps": [str]         // notable skills/experience the JD wants but the resume
                         // lacks — empty list if there are none
}}

Scoring guide:
  0.0–0.3  Poor fit — core requirements are missing
  0.3–0.6  Partial fit — some overlap but significant gaps
  0.6–0.8  Good fit — most requirements met, minor gaps
  0.8–1.0  Strong fit — closely matches role requirements

RESUME:
{resume_md}

---
JOB DESCRIPTION:
{jd_md}"""
