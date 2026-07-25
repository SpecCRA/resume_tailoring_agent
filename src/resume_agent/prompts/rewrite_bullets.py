"""Bullet-variant prompt, used once per bullet at setup time (`_ensure_bullet_
variants` in `pipelines/setup.py`): generates several phrasings of the same
accomplishment — same underlying facts, different framing (technical depth,
business impact, scale, collaboration) — so `prompts/tailor_resume.py` has real
material to choose from for whatever a given JD emphasizes. Never invents a
metric, tool, or outcome not already present in the original bullet.
"""

SYSTEM = (
    "You are an expert resume writer who crafts ATS-optimized, "
    "achievement-focused bullet points. Use strong action verbs and quantify impact "
    "only when the underlying numbers are already given to you — never invent facts, "
    "metrics, tools, or outcomes that are not present in the source material."
)


def build(bullet: str, context: str, n: int = 5) -> str:
    return f"""Rewrite the following resume bullet point {n} different ways.

Vary: action verb, emphasis, phrasing style. Keep the same underlying accomplishment.
Rules:
- Start with a strong action verb, be concise (≤20 words each).
- Quantify impact ONLY if a number, percentage, or metric already appears in the
  original bullet or context below. Do not invent, estimate, or guess at numbers,
  scale, tools, technologies, or outcomes that aren't stated.
- Do not introduce any claim (skill, responsibility, result) that isn't supported by
  the original bullet or context. Rephrasing and emphasis changes are fine; new facts
  are not.
- Where the bullet/context genuinely supports more than one valid framing (e.g.
  technical/methodological depth, business or stakeholder impact, scale or
  reliability, cross-functional collaboration), let different variants lead with
  different framings, so later job-specific tailoring has real material to choose
  from. Only use a framing the bullet/context actually supports — do not invent a
  business outcome, technical detail, or collaboration that isn't there just to
  cover a framing.

Context (role and company): {context}
Original bullet: {bullet}

Return a JSON array of {n} strings. No markdown fences, no numbering."""
