SYSTEM = "You are a job description analyst. Extract structured data. Return only valid JSON."


def build(raw_text: str, company: str, role: str) -> str:
    return f"""Extract structured data from this job description.

Company: {company}
Role: {role}

Return this JSON schema:
{{
  "looks_like_a_job_posting": bool,  // false if the text below is an error page, login
                                      // wall, cookie notice, empty/placeholder content,
                                      // or otherwise not an actual job description. If
                                      // false, leave every other field as an empty list
                                      // rather than guessing at requirements.
  "required_skills": [str],
  "preferred_skills": [str],
  "reinforced_requirements": [str],  // required skills also echoed in the responsibilities
                                      // text (not just the requirements list) — the
                                      // strongest signal for what the interview will
                                      // actually focus on. Empty list if none repeat.
  "responsibilities": [str],
  "ats_keywords": [str]    // most critical terms for ATS matching
}}

Extract every skill, tool, and technology name using its EXACT wording from the
posting — do not paraphrase, normalize, or substitute a synonym (e.g. keep
"Databricks" as "Databricks", not "cloud data platform"; keep "Spark" distinct from
"distributed compute" unless the posting itself treats them as identical). An ATS
keyword filter matches literal strings, so any paraphrasing here silently breaks
downstream matching.

Return ONLY the JSON. No markdown fences.

JOB DESCRIPTION:
{raw_text}"""
