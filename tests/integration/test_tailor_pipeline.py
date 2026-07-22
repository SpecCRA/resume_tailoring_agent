from unittest.mock import MagicMock, patch

from resume_agent.pipelines.tailor import _tailor_with_page_limit


def _fake_message(text: str):
    block = MagicMock()
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


def test_tailored_resume_retries_until_it_fits_one_page(tmp_path):
    """Only the tailored output is held to a one-page limit, with trim retries."""
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = [
        _fake_message("# Resume\n\ntoo long, pass 0"),
        _fake_message("# Resume\n\ntoo long, pass 1"),
        _fake_message("# Resume\n\nfinally fits, pass 2"),
    ]

    # First two page checks report multi-page output, third reports one page.
    page_results = iter([False, False, True])

    with (
        patch("resume_agent.tools.pdf_exporter.markdown_to_pdf", return_value=tmp_path / "x.pdf"),
        patch("resume_agent.pipelines.tailor.is_one_page", side_effect=lambda p: next(page_results)),
    ):
        result = _tailor_with_page_limit(fake_client, "base md", "jd md", 0.8, "slug", tmp_path)

    assert result == "# Resume\n\nfinally fits, pass 2"
    assert fake_client.messages.create.call_count == 3


def test_tailor_gives_up_after_max_attempts_and_returns_last_output(tmp_path, monkeypatch):
    from resume_agent.config import settings

    monkeypatch.setattr(settings, "page_trim_attempts", 2)

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = [
        _fake_message("# Resume\n\nattempt 0"),
        _fake_message("# Resume\n\nattempt 1"),
    ]

    with (
        patch("resume_agent.tools.pdf_exporter.markdown_to_pdf", return_value=tmp_path / "x.pdf"),
        patch("resume_agent.pipelines.tailor.is_one_page", return_value=False),
    ):
        result = _tailor_with_page_limit(fake_client, "base md", "jd md", 0.8, "slug", tmp_path)

    assert result == "# Resume\n\nattempt 1"
    assert fake_client.messages.create.call_count == 2
