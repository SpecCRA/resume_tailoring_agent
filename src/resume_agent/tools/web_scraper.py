import httpx
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
}
_REMOVE_TAGS = ["script", "style", "nav", "footer", "header", "aside", "noscript"]


def fetch_job_text(url: str, timeout: float = 15.0) -> str:
    """Fetch a URL and return readable text, stripping boilerplate HTML."""
    resp = httpx.get(url, headers=_HEADERS, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(_REMOVE_TAGS):
        tag.decompose()

    return soup.get_text(separator="\n", strip=True)