SYSTEM = (
    "You are an expert technical resume reviewer. Suggest closely-related skills a "
    "candidate likely has based on what's already demonstrated in their resume, for "
    "a human to review and approve — never invent skills unrelated to their actual "
    "experience. Return only valid JSON."
)


def build(resume_md: str) -> str:
    return f"""Review this resume's skills and experience. Suggest specific, closely
adjacent skills that are strongly implied by what's already there but not
explicitly listed in the Skills section — e.g. a specific API/library/binding of a
tool already listed (pandas implies NumPy is plausible), or a technology explicitly
named in a bullet but missing from the Skills list.

Do NOT suggest a skill unless you can point to specific evidence for it elsewhere
in the resume. Do NOT suggest broad or generic adjacent fields (e.g. don't suggest
"machine learning" just because they know Python) — only concrete, specific,
defensible additions. These are suggestions for a human to review, not additions to
the resume — when in doubt, leave it out.

Return this exact JSON schema — no markdown fences:
{{
  "suggestions": [
    {{"skill": str, "evidence": str}}   // evidence: the specific existing skill or
                                         // bullet that supports this suggestion
  ]
}}
(empty list if there's nothing worth suggesting)

RESUME:
{resume_md}"""
