SYSTEM = (
    "You are an expert resume coach. Select and tailor resume content "
    "to maximize ATS score and recruiter relevance for a specific job."
)


def build(resume_md: str, jd_md: str, fit_score: float, trim_pass: int = 0) -> str:
    trim_note = (
        f"\n\nIMPORTANT: This is trim pass {trim_pass}. The previous output exceeded one page. "
        "Remove the least-relevant bullets and shorten descriptions until it fits on one page."
        if trim_pass > 0
        else ""
    )
    return f"""Tailor the resume below for the job description provided.

Rules:
1. Select the SINGLE BEST bullet variant for each bullet point (most relevant to JD).
2. Reorder skills to front-load keywords from the job description.
3. Omit experience sections with zero relevance to the role.
4. Keep the summary focused on the exact role and company.
5. Output ATS-safe markdown: no tables, no columns, plain section headers.
6. Format: # Name, contact line, ## Summary, ## Skills, ## Experience, ## Education, ## Projects
7. Fit score context: {fit_score:.0%} match — {'prioritize best fit' if fit_score > 0.7 else 'note skills gaps clearly in summary'}.
{trim_note}

---
RESUME (all variants):
{resume_md}

---
JOB DESCRIPTION:
{jd_md}

Output ONLY the tailored markdown resume."""