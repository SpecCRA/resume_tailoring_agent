from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(help="Resume tailoring agent powered by Claude.")


@app.command()
def setup(
    pdf: Annotated[Path, typer.Argument(help="Path to your resume PDF")],
) -> None:
    """One-time setup: parse PDF resume and generate base template with bullet variants."""
    from resume_agent.pipelines.setup import run_setup
    run_setup(str(pdf))


@app.command()
def review() -> None:
    """Re-review a manually-edited base_resume.md and backfill variants for new bullets."""
    from resume_agent.pipelines.setup import run_review_base
    run_review_base()


@app.command()
def tailor(
    url:     Annotated[str, typer.Argument(help="Job posting URL")],
    company: Annotated[str, typer.Option("--company", "-c", help="Company name")],
    role:    Annotated[str, typer.Option("--role",    "-r", help="Job title")],
) -> None:
    """Tailor resume for a specific job posting and export to PDF."""
    from resume_agent.pipelines.tailor import run_tailor
    run_tailor(url, company, role)


if __name__ == "__main__":
    app()