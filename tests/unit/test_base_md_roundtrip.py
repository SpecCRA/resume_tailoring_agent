from resume_agent.models.resume import (
    BulletPoint,
    EducationEntry,
    ExperienceEntry,
    ProjectEntry,
    Resume,
)
from resume_agent.pipelines.setup import _parse_base_md, _render_base_md

RESUME = Resume(
    name="Jordan Rivera",
    email="jordan@example.com",
    phone="555-0100",
    linkedin="linkedin.com/in/jordan",
    github="github.com/jordan",
    location="Remote",
    summary="Senior engineer with a decade of experience.",
    skills=["Python", "SQL", "Kubernetes"],
    experience=[
        ExperienceEntry(
            company="Acme Corp",
            title="Senior Engineer",
            dates="2019-2023",
            location="NYC",
            bullets=[
                BulletPoint(original="Shipped the thing", variants=["Delivered the thing", "Built the thing"]),
                BulletPoint(original="Freshly added bullet with no variants yet"),
            ],
        ),
    ],
    education=[
        EducationEntry(institution="State University", degree="B.S. Computer Science", dates="2011-2015", gpa=3.8),
    ],
    projects=[
        ProjectEntry(
            name="Side Project",
            description="A weekend build.",
            url="https://example.com/project",
            bullets=[BulletPoint(original="Built a thing end to end", variants=["Engineered a thing"])],
        ),
    ],
)


def test_render_then_parse_round_trips_to_the_same_resume():
    parsed = _parse_base_md(_render_base_md(RESUME))
    assert parsed == RESUME


def test_manually_added_bullet_survives_round_trip_without_variants():
    parsed = _parse_base_md(_render_base_md(RESUME))
    new_bullet = parsed.experience[0].bullets[1]
    assert new_bullet.original == "Freshly added bullet with no variants yet"
    assert new_bullet.variants == []


def test_headline_round_trips_when_present():
    resume_with_headline = RESUME.model_copy(update={"headline": "Senior Data Engineer"})
    parsed = _parse_base_md(_render_base_md(resume_with_headline))
    assert parsed == resume_with_headline
