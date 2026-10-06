"""Refinement prompt: a second (and third, ...) tailoring pass that folds the
prior `review_output.py` pass's own findings — its `remaining_gaps` and
`improvement_suggestions` — back in as extra input, so the resume can improve
past whatever the first tailoring pass produced instead of stopping there.

Deliberately reuses `tailor_resume.build()` for the entire rule set (anti­
fabrication, anchors, formatting, bullet-provenance, trim/always-include
handling) rather than restating it — refining is still "select/rewrite bullets
for this JD from the full base resume," just with one more input appended.
Re-derives from the full base resume each time (not a diff of the previous
tailored output), the same way the first pass does, so there's one source of
truth for what a tailored resume may contain and no risk of compounding drift
across iterations.

Called in a loop by `pipelines/tailor.py._refine_until_no_improvement`, which
stops as soon as an iteration's reviewed fit_score fails to beat the previous
best, or after `settings.max_refine_attempts` tries — whichever comes first.
"""

from typing import Any

from resume_agent.prompts import tailor_resume

SYSTEM = tailor_resume.SYSTEM


def build(
    resume_md: str,
    jd_md: str,
    remaining_gaps: list[str],
    improvement_suggestions: list[dict[str, Any]],
    trim_pass: int = 0,
    always_include_title: str | None = None,
) -> str:
    base_prompt = tailor_resume.build(
        resume_md, jd_md, trim_pass=trim_pass, always_include_title=always_include_title
    )
    gaps_block = "\n".join(f"- {g}" for g in remaining_gaps) or "(none)"
    suggestion_block = "\n".join(
        f"- {s['suggestion']} (evidence: {s['evidence']}; addresses: {s['addresses']})"
        for s in improvement_suggestions
    ) or "(none)"
    return f"""{base_prompt}

---
A prior tailoring attempt was already reviewed against this job description. Revise
your selection further using that review's findings below, still following every
rule above without exception — in particular rule 10 (never invent anything not
already in the resume above, even to close one of these gaps).

REMAINING GAPS (the JD wants something the previous attempt still didn't show — act
on one only if the base resume above genuinely supports it; otherwise leave it as a
silent omission, exactly as rule 10 already requires):
{gaps_block}

SUGGESTED IMPROVEMENTS (a reviewer already checked each of these against the base
resume above — e.g. an unused bullet variant, a skill demonstrated but unlisted —
so they're grounded, not speculative. Apply whichever genuinely improve fit for
this JD; skip any that would hurt focus, relevance, or the one-page limit):
{suggestion_block}

Output ONLY the revised tailored markdown resume, same format as before."""
