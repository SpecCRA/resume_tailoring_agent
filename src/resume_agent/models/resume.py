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
    # Contact
    name: str
    email: str
    phone: str
    linkedin: str | None = None
    github: str | None = None
    location: str | None = None

    # Content
    summary: str | None = None
    skills: list[str]
    experience: list[ExperienceEntry]
    education: list[EducationEntry]
    projects: list[ProjectEntry]


class TailoredResume(BaseModel):
    """Subset of Resume with only the selected bullets for a given job."""
    name: str
    email: str
    phone: str
    linkedin: str | None = None
    github: str | None = None
    location: str | None = None
    summary: str
    skills: list[str]
    experience: list[ExperienceEntry]
    education: list[EducationEntry]
    projects: list[ProjectEntry]
    fit_score: float       # 0.0 – 1.0
    fit_notes: str         # LLM explanation of match quality