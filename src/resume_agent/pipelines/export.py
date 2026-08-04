"""Standalone pipeline: an existing markdown resume file -> PDF, no LLM calls.

The non-agentic sibling of the PDF-export step inside `pipelines/tailor.py` —
for re-exporting `base_resume.md`, a previously tailored `<slug>.md`, or any
other hand-edited resume markdown after tweaking its content or the PDF
stylesheet, without re-running scraping, fit assessment, or tailoring.

Reuses the same one-page check `pipelines/tailor.py._tailor_with_page_limit`
enforces during tailoring — since this path has no LLM in the loop to trim
content and retry, a page-count violation here is raised as an error instead of
auto-corrected.
"""

from pathlib import Path

from resume_agent.errors import MarkdownFileNotFoundError, PageLimitExceededError
from resume_agent.tools.page_validator import count_pages, is_one_page
from resume_agent.tools.pdf_exporter import markdown_to_pdf


def run_export(md_path: str, output_path: str | None = None) -> Path:
    """
    Render an existing markdown resume file to PDF.
    `output_path` defaults to the input path with its suffix swapped to `.pdf`.
    Returns the path to the generated PDF. Raises `PageLimitExceededError` if the
    rendered PDF doesn't fit on a single page.
    """
    source = Path(md_path)
    if not source.is_file():
        raise MarkdownFileNotFoundError(f"No markdown file found at {source}")

    destination = Path(output_path) if output_path else source.with_suffix(".pdf")
    pdf_path = markdown_to_pdf(source.read_text(), destination)

    if not is_one_page(pdf_path):
        raise PageLimitExceededError(
            f"Exported PDF at {pdf_path} is {count_pages(pdf_path)} pages — "
            "resumes must fit on a single page. Trim the source markdown and re-export."
        )

    return pdf_path
