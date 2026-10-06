"""Deterministic, LLM-free ATS keyword matching — whether a `tailor`-produced
resume literally contains the keywords `prompts/extract_and_assess.py` pulled out
of a job posting. Coverage is a claim about literal string matches, not something
to trust an LLM's judgment on, so this stays plain Python rather than a prompt.

Used by `pipelines/tailor.py` both right after the initial tailor pass and after
every refinement round, to report ATS coverage and to decide what's still
missing for `review_output.py`'s `remaining_gaps`.
"""

import re

_ALTERNATION_RE = re.compile(r"\s+or\s+|/", re.IGNORECASE)


def keyword_alternatives(keyword: str) -> list[str]:
    """Split a compound keyword like 'ETL/ELT' or 'Spark or Flink' into the
    individual alternatives a JD author meant as interchangeable, so coverage
    counts a hit if the resume literally contains any ONE of them — postings
    routinely list acceptable equivalents this way (ETL/ELT, CI/CD, batch/
    streaming, "Spark or Flink", "AWS/GCP/Azure").

    Guards against degenerate splits like "A/B testing" (which would otherwise
    yield a bare "A") by only splitting when every resulting piece is at least
    two characters — short of that, the "/" is probably part of the term
    itself rather than a separator between two independent keywords.
    """
    parts = [p.strip() for p in _ALTERNATION_RE.split(keyword) if p.strip()]
    if len(parts) > 1 and all(len(p) >= 2 for p in parts):
        return parts
    return [keyword]


def ats_keyword_coverage(tailored_md: str, ats_keywords: list[str]) -> tuple[list[str], list[str]]:
    """Case-insensitive substring check of which `ats_keywords` literally appear in
    the tailored markdown — each keyword first expanded into its alternatives (see
    `keyword_alternatives`) so a match on any one equivalent term counts.
    Returns (found, missing), each preserving the order of `ats_keywords`.
    """
    haystack = tailored_md.lower()
    found = []
    missing = []
    for kw in ats_keywords:
        if any(alt.lower() in haystack for alt in keyword_alternatives(kw)):
            found.append(kw)
        else:
            missing.append(kw)
    return found, missing
