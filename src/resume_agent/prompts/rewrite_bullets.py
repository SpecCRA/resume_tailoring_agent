"""Bullet-variant prompt, used at setup time (`_generate_all_bullet_variants` in
`pipelines/setup.py`) to backfill every bullet lacking variants in a single batched
call: generates several phrasings of the same accomplishment per bullet — same
underlying facts, different framing (technical depth, business impact, scale,
collaboration) — so `prompts/tailor_resume.py` has real material to choose from for
whatever a given JD emphasizes. Never invents a metric, tool, or outcome not already
present in the original bullet.

Batched rather than one call per bullet purely to cut round trips — a resume with a
handful of jobs/projects otherwise means a handful of near-identical LLM calls, each
re-paying the same system-prompt and rule-list overhead for a single short output.
"""

import json
from typing import Any

SYSTEM = (
    "You are an expert resume writer who crafts ATS-optimized, "
    "achievement-focused bullet points. Use strong action verbs and quantify impact "
    "only when the underlying numbers are already given to you — never invent facts, "
    "metrics, tools, or outcomes that are not present in the source material."
)


def build(items: list[dict[str, Any]]) -> str:
    items_json = json.dumps(items, indent=2)
    return f"""Rewrite each of the following resume bullets multiple different ways
(the exact count per bullet is given by its "n" field).

Vary: action verb, emphasis, phrasing style. Keep the same underlying accomplishment.
Rules, applied independently to every bullet:
- Start with a strong action verb, be concise (≤20 words each).
- Quantify impact ONLY if a number, percentage, or metric already appears in that
  bullet's original text or context. Do not invent, estimate, or guess at numbers,
  scale, tools, technologies, or outcomes that aren't stated.
- Do not introduce any claim (skill, responsibility, result) that isn't supported by
  the original bullet or its context. Rephrasing and emphasis changes are fine; new
  facts are not.
- Where the bullet/context genuinely supports more than one valid framing (e.g.
  technical/methodological depth, business or stakeholder impact, scale or
  reliability, cross-functional collaboration), let different variants lead with
  different framings, so later job-specific tailoring has real material to choose
  from. Only use a framing the bullet/context actually supports — do not invent a
  business outcome, technical detail, or collaboration that isn't there just to
  cover a framing.

Bullets to rewrite:
{items_json}

Return this exact JSON schema — no markdown fences:
{{
  "bullets": [
    {{"id": int, "variants": [str, ...]}}   // exactly "n" variants for that bullet's id
  ]
}}
Include exactly one entry per input id (order doesn't matter) — every id above must
appear exactly once in the response."""
