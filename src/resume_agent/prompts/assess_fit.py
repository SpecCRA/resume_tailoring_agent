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
