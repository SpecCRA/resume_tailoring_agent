SYSTEM = (
    "You are an expert technical recruiter and resume coach. "
    "Evaluate resume-to-job fit objectively and return only valid JSON."
)


def build(resume_md: str, jd_md: str) -> str:
    return f"""Score how well this resume matches the job description.

Return this exact JSON schema — no markdown fences:
{{
  "score": float,              // 0.0 (no match) to 1.0 (perfect match)
  "matched_skills": [str],     // skills present in both resume and JD
  "missing_skills": [str],     // required/preferred skills absent from resume
  "matched_experience": [str], // resume experience directly relevant to the role
  "gaps": [str],               // notable experience gaps for this role
  "suggestions": [str],        // specific additions that would improve fit
  "notes": str                 // 1-2 sentence overall assessment
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