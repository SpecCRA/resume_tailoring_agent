"""The structured response every critique persona in `prompts/critique.py` must
return — mirrors the pattern `models/resume.py`/`models/job.py` already use for
their own LLM-produced data: validate immediately after the call so a
schema-violating response becomes a clean, caught error at the source (in
`pipelines/critique.py`) instead of a bare `KeyError` surfacing later, deep
inside `_render_critique_md`.
"""

from typing import Literal

from pydantic import BaseModel


class Finding(BaseModel):
    severity: Literal["high", "medium", "low"]
    location: str
    note: str


class CritiqueResult(BaseModel):
    verdict: Literal["pass", "flag"]
    findings: list[Finding] = []
