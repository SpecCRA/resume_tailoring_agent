"""The structured job posting produced by `prompts/extract_and_assess.py` — a scraped JD's
raw text plus the skills/requirements/keywords the LLM pulled out of it. Rendered
to `job.md` by `pipelines/tailor.py._render_jd_md` and consumed by both the fit
assessment and the tailoring prompt.

`ExtractAndAssessResult` is the full raw shape `prompts/extract_and_assess.py`
returns in one call — the JD-extraction fields above plus the per-call fit
assessment (`fit_score`/`reasoning`/`gaps`/`looks_like_a_job_posting`), which
aren't part of `JobDescription` since they're not persisted to `job.md` or
reused by later pipeline steps. Validating this immediately after the call
(see `pipelines/tailor.py`) catches a malformed response at the source instead
of a bare `KeyError` surfacing wherever `data["fit_score"]` etc. was read.
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


class ExtractAndAssessResult(BaseModel):
    looks_like_a_job_posting: bool = True
    required_skills: list[str]
    preferred_skills: list[str]
    reinforced_requirements: list[str]
    responsibilities: list[str]
    ats_keywords: list[str]
    fit_score: float
    reasoning: str
    gaps: list[str]
