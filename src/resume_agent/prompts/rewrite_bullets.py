SYSTEM = (
    "You are an expert resume writer who crafts ATS-optimized, "
    "achievement-focused bullet points. Use strong action verbs and quantify impact."
)


def build(bullet: str, context: str, n: int = 5) -> str:
    return f"""Rewrite the following resume bullet point {n} different ways.

Vary: action verb, emphasis, phrasing style. Keep the same underlying accomplishment.
Rules: start with a strong action verb, be concise (≤20 words each), quantify where possible.

Context (role and company): {context}
Original bullet: {bullet}

Return a JSON array of {n} strings. No markdown fences, no numbering."""