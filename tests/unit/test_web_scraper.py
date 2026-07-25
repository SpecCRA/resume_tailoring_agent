import httpx
import pytest

from resume_agent.errors import ScrapingError
from resume_agent.tools.web_scraper import fetch_job_text


def test_fetch_job_text_raises_scraping_error_on_http_failure(respx_mock):
    respx_mock.get("https://example.com/job").mock(return_value=httpx.Response(500))

    with pytest.raises(ScrapingError):
        fetch_job_text("https://example.com/job")


def test_fetch_job_text_strips_boilerplate_tags(respx_mock):
    html = "<html><body><nav>Site Nav</nav><p>Job description text</p></body></html>"
    respx_mock.get("https://example.com/job").mock(return_value=httpx.Response(200, html=html))

    text = fetch_job_text("https://example.com/job")

    assert "Job description text" in text
    assert "Site Nav" not in text
