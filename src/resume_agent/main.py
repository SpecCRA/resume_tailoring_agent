from pathlib import Path
from typing import Annotated

import typer
from rich import print as rprint

app = typer.Typer(help="Resume tailoring agent powered by Claude.")


@app.command()
def setup(
    pdf: Annotated[Path, typer.Argument(help="Path to your resume PDF")],
) -> None:
    """One-time setup: parse PDF resume and generate base template with bullet variants."""
    from resume_agent.errors import ResumeAgentError
    from resume_agent.pipelines.setup import run_setup
    try:
        run_setup(str(pdf))
    except ResumeAgentError as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e


@app.command()
def review() -> None:
    """Re-review a manually-edited base_resume.md and backfill variants for new bullets."""
    from resume_agent.errors import ResumeAgentError
    from resume_agent.pipelines.setup import run_review_base
    try:
        run_review_base()
    except ResumeAgentError as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e


@app.command()
def tailor(
    url:     Annotated[str, typer.Argument(help="Job posting URL")],
    company: Annotated[str, typer.Option("--company", "-c", help="Company name")],
    role:    Annotated[str, typer.Option("--role",    "-r", help="Job title")],
) -> None:
    """Tailor resume for a specific job posting and export to PDF."""
    from resume_agent.errors import ResumeAgentError
    from resume_agent.pipelines.tailor import run_tailor
    try:
        run_tailor(url, company, role)
    except ResumeAgentError as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e


if __name__ == "__main__":
    app()
