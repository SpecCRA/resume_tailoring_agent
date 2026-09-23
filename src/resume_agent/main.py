"""CLI entry point (Typer). Exposes five commands — `setup`, `review`, `tailor`,
`export`, `critique` — each a thin wrapper around a pipeline function in
`pipelines/`. All five catch `ResumeAgentError` (see `errors.py`) and print a
clean message instead of letting a scraping/LLM/validation failure surface as
a raw traceback.
"""

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


@app.command()
def export(
    markdown: Annotated[Path, typer.Argument(help="Path to an existing markdown resume")],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output PDF path (defaults next to the input file)"),
    ] = None,
) -> None:
    """Export an existing markdown resume straight to PDF — no LLM calls."""
    from resume_agent.errors import ResumeAgentError
    from resume_agent.pipelines.export import run_export
    try:
        pdf_path = run_export(str(markdown), str(output) if output else None)
        rprint(f"[green]Done![/green] PDF → {pdf_path}")
    except ResumeAgentError as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e


@app.command()
def critique(
    slug: Annotated[
        str,
        typer.Argument(help="Job slug, e.g. acme-corp-data-engineer (output/<slug>.md)"),
    ],
) -> None:
    """Run a 5-persona critique (ATS parser, recruiter, hiring manager, integrity
    auditor, narrative coherence) on an already-tailored resume. Opt-in — not run
    automatically by `tailor` — since it's five extra LLM calls and advisory only."""
    from resume_agent.errors import ResumeAgentError
    from resume_agent.pipelines.critique import run_critique
    try:
        report_path = run_critique(slug)
        rprint(f"[green]Done![/green] Critique → {report_path}")
    except ResumeAgentError as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e


if __name__ == "__main__":
    app()
