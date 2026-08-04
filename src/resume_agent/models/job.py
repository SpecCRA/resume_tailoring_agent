"""The structured job posting produced by `prompts/extract_and_assess.py` — a scraped JD's
raw text plus the skills/requirements/keywords the LLM pulled out of it. Rendered
to `job.md` by `pipelines/tailor.py._render_jd_md` and consumed by both the fit
assessment and the tailoring prompt.
"""

from pydantic import BaseModel


class JobDescription(BaseModel):
    company: str
    role: str
    url: str
    slug: str  # e.g. "discord-data-engineer-2024"
    raw_text: str
    required_skills: list[str]
    preferred_skills: list[str]
    reinforced_requirements: list[str]  # required skills echoed in responsibilities too
    responsibilities: list[str]
    ats_keywords: list[str]  # Critical terms for keyword matching
