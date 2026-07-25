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
