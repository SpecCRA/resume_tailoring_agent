SYSTEM = "You are a job description analyst. Extract structured data. Return only valid JSON."


def build(raw_text: str, company: str, role: str) -> str:
    return f"""Extract structured data from this job description.

Company: {company}
Role: {role}

Return this JSON schema:
{{
  "required_skills": [str],
  "preferred_skills": [str],
  "responsibilities": [str],
  "ats_keywords": [str]    // most critical terms for ATS matching
}}

Return ONLY the JSON. No markdown fences.

JOB DESCRIPTION:
{raw_text}"""