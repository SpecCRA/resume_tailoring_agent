"""The structured response `prompts/review_output.py` must return — mirrors the
pattern `models/resume.py`/`models/critique.py` already use for their own
LLM-produced data: validate immediately after the call so a schema-violating
response becomes a clean, caught `LLMResponseError` at the call site (in
`pipelines/tailor.py`) instead of a bare `KeyError` surfacing later, deep
inside `_render_assessment_md` or the refine loop.
"""

from typing import Literal

from pydantic import BaseModel


class BulletReview(BaseModel):
    bullet: str
    supports: list[str]
    relevance: Literal["high", "medium", "low"]
    reason: str


class ImprovementSuggestion(BaseModel):
    suggestion: str
    evidence: str
    addresses: str


class TailoredResumeReview(BaseModel):
    fit_score: float
    reasoning: str
    remaining_gaps: list[str]
    bullet_reviews: list[BulletReview]
    improvement_suggestions: list[ImprovementSuggestion] = []
