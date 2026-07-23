SYSTEM = (
    "You are an expert resume parser. Extract ALL content faithfully — "
    "do not summarize or rewrite. Return only valid JSON."
)


def build(raw_text: str) -> str:
    return f"""Parse the resume below into this exact JSON schema:

{{
  "name": str,
  "email": str,
  "phone": str,
  "linkedin": str | null,
  "github": str | null,
  "location": str | null,
  "summary": str | null,
  "skills": [str],
  "experience": [
    {{
      "company": str,
      "title": str,
      "dates": str,
      "location": str | null,
      "bullets": [{{"original": str}}]
    }}
  ],
  "education": [
    {{"institution": str, "degree": str, "dates": str, "gpa": float | null}}
  ],
  "projects": [
    {{"name": str, "description": str | null, "bullets": [{{"original": str}}], "url": str | null}}
  ]
}}

Return ONLY the JSON object, no markdown fences.

RESUME:
{raw_text}"""