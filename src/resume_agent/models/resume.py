from pydantic import BaseModel, Field


class BulletPoint(BaseModel):
    original: str
    variants: list[str] = Field(default_factory=list)  # 3-5 LLM rewrites


class ExperienceEntry(BaseModel):
    company: str
    title: str
    dates: str
    location: str | None = None
    bullets: list[BulletPoint]


class EducationEntry(BaseModel):
    institution: str
    degree: str
    dates: str
    gpa: float | None = None


class ProjectEntry(BaseModel):
    name: str
    description: str | None = None
    bullets: list[BulletPoint]
    url: str | None = None


class Resume(BaseModel):
    # Contact — always present; use "" (not None) when the source resume lacks a field.
    name: str
    email: str
    phone: str
    linkedin: str
    github: str
    location: str

    # Content
    headline: str | None = None  # title line under the name, e.g. "Senior Data Engineer"
    summary: str | None = None
    skills: list[str]
    experience: list[ExperienceEntry]
    education: list[EducationEntry]
    projects: list[ProjectEntry]
