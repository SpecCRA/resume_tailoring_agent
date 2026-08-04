"""Combined JD-extraction + fit-assessment prompt: turns raw scraped posting text
into a structured `JobDescription` AND scores the candidate's resume against it, in
one call. Replaces the old two-call `extract_jd.py` + `assess_fit.py` pair — both of
those ran unconditionally on every `tailor` invocation (including postings that get
screened out below `min_fit_score`), making this the highest-frequency call pair in
the pipeline. Merging them halves that fixed per-job screening cost.

Extracts skill/keyword terms verbatim (never paraphrased, so downstream ATS-keyword
matching isn't silently broken) and flags content that isn't actually a job posting
(`looks_like_a_job_posting`) so `pipelines/tailor.py` can reject a bad scrape instead
of tailoring — or scoring fit — against fabricated requirements.
"""

SYSTEM = (
    "You are a job description analyst and expert technical recruiter. Extract "
    "structured data from a job posting and assess how well a candidate's resume "
    "matches it. Return only valid JSON."
)


def build(raw_text: str, company: str, role: str, resume_md: str) -> str:
    return f"""Extract structured data from the job description below, and assess how
well the given resume matches it.

Company: {company}
Role: {role}

Return this JSON schema:
{{
  "looks_like_a_job_posting": bool,  // false if the text below is an error page, login
                                      // wall, cookie notice, empty/placeholder content,
                                      // or otherwise not an actual job description. If
                                      // false, leave every extraction field as an empty
                                      // list rather than guessing at requirements, and
                                      // set fit_score to 0.0, gaps to [], and reasoning
                                      // to a short note that this isn't a real posting —
                                      // don't guess at a fit assessment either.
  "required_skills": [str],
  "preferred_skills": [str],
  "reinforced_requirements": [str],  // required skills also echoed in the responsibilities
                                      // text (not just the requirements list) — the
                                      // strongest signal for what the interview will
                                      // actually focus on. Empty list if none repeat.
  "responsibilities": [str],
  "ats_keywords": [str],   // most critical terms for ATS matching
  "fit_score": float,      // 0.0 (no overlap) to 1.0 (excellent match)
  "reasoning": str,        // 1-2 sentence explanation of the fit score
  "gaps": [str]            // notable skills/experience the JD wants but the resume
                            // lacks — empty list if there are none
}}

Extract every skill, tool, and technology name using its EXACT wording from the
posting — do not paraphrase, normalize, or substitute a synonym (e.g. keep
"Databricks" as "Databricks", not "cloud data platform"; keep "Spark" distinct from
"distributed compute" unless the posting itself treats them as identical). An ATS
keyword filter matches literal strings, so any paraphrasing here silently breaks
downstream matching.

For "ats_keywords" specifically: prefer concrete, literally-matchable tool/technology
names over abstract category phrases. Postings in data science, data engineering, and
ML routinely name a category and then give concrete examples right next to it — in
parentheses, after "e.g.", "such as", "like", or in a comma list — e.g. "distributed
computing frameworks (Spark, Databricks)", "cloud platforms (AWS, GCP, or Azure)",
"orchestration tools like Airflow or Dagster", "ML frameworks such as TensorFlow and
PyTorch", "data warehouses (Snowflake, BigQuery)". When the posting does this, extract
the NAMED tools as their own ats_keywords entries instead of (or in addition to) the
umbrella category phrase — a resume can literally contain "Databricks" but will almost
never literally contain "distributed computing frameworks". Only keep a bare category
phrase as an ats_keyword when the posting never names a concrete instance of it
anywhere; in that case there's nothing literal to match against, so the requirement
belongs in required_skills/preferred_skills (judged qualitatively in fit_score/gaps)
rather than ats_keywords.

Fit-scoring guide:
  0.0–0.3  Poor fit — core requirements are missing
  0.3–0.6  Partial fit — some overlap but significant gaps
  0.6–0.8  Good fit — most requirements met, minor gaps
  0.8–1.0  Strong fit — closely matches role requirements

Return ONLY the JSON. No markdown fences.

JOB DESCRIPTION:
{raw_text}

---
RESUME:
{resume_md}"""
