"""Fetches a job-posting URL and returns its readable text, with obvious
boilerplate tags (nav/footer/script/etc.) stripped, before it's handed to
`prompts/extract_and_assess.py`. Network/HTTP failures are converted to `ScrapingError`
rather than a raw `httpx` exception; the *content* of what comes back (e.g. an
empty JS-rendered page) is validated separately, in `pipelines/tailor.py`.
"""

import httpx
from bs4 import BeautifulSoup

from resume_agent.errors import ScrapingError

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
}
_REMOVE_TAGS = ["script", "style", "nav", "footer", "header", "aside", "noscript"]


def fetch_job_text(url: str, timeout: float = 15.0) -> str:
    """Fetch a URL and return readable text, stripping boilerplate HTML."""
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise ScrapingError(f"Failed to fetch job posting from {url}: {e}") from e

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(_REMOVE_TAGS):
        tag.decompose()

    return soup.get_text(separator="\n", strip=True)