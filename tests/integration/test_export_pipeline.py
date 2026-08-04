from unittest.mock import patch

import pytest

from resume_agent.errors import MarkdownFileNotFoundError, PageLimitExceededError
from resume_agent.pipelines.export import run_export


def test_run_export_renders_markdown_to_default_pdf_path(tmp_path):
    md_path = tmp_path / "acme-platform-engineer.md"
    md_path.write_text("# Jordan Rivera\n\n## Experience\n- Shipped a thing\n")

    with (
        patch("resume_agent.pipelines.export.markdown_to_pdf") as mock_export,
        patch("resume_agent.pipelines.export.is_one_page", return_value=True),
    ):
        mock_export.return_value = md_path.with_suffix(".pdf")
        result = run_export(str(md_path))

    mock_export.assert_called_once_with(md_path.read_text(), md_path.with_suffix(".pdf"))
    assert result == md_path.with_suffix(".pdf")


def test_run_export_honors_explicit_output_path(tmp_path):
    md_path = tmp_path / "resume.md"
    md_path.write_text("# Jordan Rivera\n")
    custom_output = tmp_path / "custom" / "out.pdf"

    with (
        patch("resume_agent.pipelines.export.markdown_to_pdf") as mock_export,
        patch("resume_agent.pipelines.export.is_one_page", return_value=True),
    ):
        mock_export.return_value = custom_output
        result = run_export(str(md_path), str(custom_output))

    mock_export.assert_called_once_with(md_path.read_text(), custom_output)
    assert result == custom_output


def test_run_export_rejects_missing_file(tmp_path):
    with pytest.raises(MarkdownFileNotFoundError):
        run_export(str(tmp_path / "does-not-exist.md"))


def test_run_export_rejects_multi_page_pdf(tmp_path):
    md_path = tmp_path / "resume.md"
    md_path.write_text("# Jordan Rivera\n\n## Experience\n- Shipped a thing\n")

    with (
        patch("resume_agent.pipelines.export.markdown_to_pdf") as mock_export,
        patch("resume_agent.pipelines.export.is_one_page", return_value=False),
        patch("resume_agent.pipelines.export.count_pages", return_value=2),
    ):
        mock_export.return_value = md_path.with_suffix(".pdf")
        with pytest.raises(PageLimitExceededError):
            run_export(str(md_path))
