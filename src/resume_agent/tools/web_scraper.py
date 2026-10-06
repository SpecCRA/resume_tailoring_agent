"""Fetches a job-posting URL and returns its readable text, with obvious
boilerplate tags (nav/footer/script/etc.) stripped, before it's handed to
`prompts/extract_and_assess.py`. Network/HTTP failures are converted to `ScrapingError`
rather than a raw `httpx` exception; the *content* of what comes back (e.g. an
empty JS-rendered page) is validated separately, in `pipelines/tailor.py`.

Some company career pages (e.g. a Squarespace site) embed Ashby's job-board
widget rather than hosting the posting themselves — identifiable by an
`ashby_jid=<id>` query param — and that widget renders the actual posting
client-side with JavaScript, so a plain GET only ever returns the embedding
page's shell (nav/meta tags, no job content), regardless of how long the
timeout is. `_resolve_ashby_embed_url` detects that pattern and redirects to
Ashby's own hosted job page for the same posting instead
(`jobs.ashbyhq.com/<board>/<id>`).

That hosted page (and many other ATS-hosted job boards) still doesn't put the
posting in the visible DOM at all — it's a client-rendered SPA that populates
the page via JS a plain GET never runs. What IS present server-side, because
Google for Jobs indexing depends on it, is a `schema.org JobPosting` block in
a `<script type="application/ld+json">` tag. `_extract_json_ld_description`
pulls the posting straight out of that structured block when present, which
is both more complete and more reliable than scraping whatever's left of the
visible DOM.

Neither trick helps every ATS platform, though — some (Oracle HCM/Taleo-style
"Candidate Experience" portals, among others) serve a near-empty HTML shell
with no JSON-LD and no discoverable public API, and populate everything
through client-side JavaScript with no server-rendered fallback at all.
`_fetch_rendered_text` is the general fallback for that: render the page in a
real (headless) browser via Playwright — actually executing its JavaScript,
like a real visitor's browser would — and read the text back out of whichever
frame on the page has the most of it (a third-party widget like Ashby's is
commonly iframed, so the posting can live in a frame other than the page's
own). It's slow and has a heavier dependency than the tricks above, so
`fetch_job_text` only reaches for it once those faster paths have been tried
and still come up short (below `settings.min_jd_chars`). If Playwright or its
browser binary isn't installed, this fails soft (falls back to whatever the
fast path already had) rather than raising an unrelated crash — the shorter
text still triggers pipelines/tailor.py's existing, informative length-gate
error either way.

The Ashby-embed redirect above is *not* superseded by the general render
fallback, even though both are trying to solve "the real content isn't in
this page" — Ashby's widget turns out to live inside an iframe that a plain
top-level render doesn't reach, so the redirect is currently the only thing
that makes that case work at all, not a faster shortcut to the same result.
It's registered in `_EMBED_REDIRECT_RESOLVERS` — a small, explicit table of
known-platform detectors, tried before the general fallback purely because
redirecting straight to a platform's own hosted page is faster and more
reliable than a multi-second browser launch. Adding the next platform-specific
quirk means adding one resolver function to that list, not threading new logic
through `fetch_job_text` itself.
"""

import json
import re
from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from resume_agent.config import settings
from resume_agent.errors import ScrapingError

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
}
_REMOVE_TAGS = ["script", "style", "nav", "footer", "header", "aside", "noscript"]

_ASHBY_JID_PARAM = "ashby_jid"
_ASHBY_BOARD_RE = re.compile(r"ashbyhq\.com/([a-zA-Z0-9_-]+)/embed")


def fetch_job_text(url: str, timeout: float = 15.0) -> str:
    """Fetch a URL and return readable text, stripping boilerplate HTML."""
    html = _get(url, timeout)

    redirect_url = _resolve_known_embed_redirect(url, html)
    if redirect_url is not None:
        html = _get(redirect_url, timeout)
        url = redirect_url

    text = _extract_json_ld_description(html) or _visible_text(html)
    if len(text.strip()) >= settings.min_jd_chars:
        return text

    rendered_text = _fetch_rendered_text(url, timeout)
    if rendered_text is not None and len(rendered_text.strip()) > len(text.strip()):
        return rendered_text
    return text


def _visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_REMOVE_TAGS):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _get(url: str, timeout: float) -> str:
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise ScrapingError(f"Failed to fetch job posting from {url}: {e}") from e
    return resp.text


def _resolve_ashby_embed_url(url: str, html: str) -> str | None:
    """If `url` has an `ashby_jid` query param (an Ashby job-board widget
    embedded on someone else's site), find that org's Ashby board slug in the
    embedding page's own HTML (present in the widget's script src even though
    the posting content isn't) and return Ashby's own hosted URL for the same
    job — else None. The board slug isn't derivable from the embedding site's
    domain, so it has to come from the page itself.
    """
    job_id = parse_qs(urlparse(url).query).get(_ASHBY_JID_PARAM, [None])[0]
    if job_id is None:
        return None
    match = _ASHBY_BOARD_RE.search(html)
    if match is None:
        return None
    return f"https://jobs.ashbyhq.com/{match.group(1)}/{job_id}"


# Known ATS-embed-widget detectors, tried in order — each takes (url, html)
# for the originally-requested page and returns that platform's own hosted
# URL for the same posting, or None if it doesn't recognize this page. Add a
# new platform's quirk here, not by threading more logic through
# fetch_job_text itself.
_EMBED_REDIRECT_RESOLVERS: list[Callable[[str, str], str | None]] = [
    _resolve_ashby_embed_url,
]


def _resolve_known_embed_redirect(url: str, html: str) -> str | None:
    """Check `url`/`html` against every known ATS-embed-widget detector and
    return the first match's redirect URL, or None if none recognize it.
    Tried before the general render fallback purely because a redirect is a
    fast, reliable shortcut when a platform is recognized — not because the
    render fallback can't eventually replace it for every case (it currently
    can't for at least one: see the module docstring on Ashby's iframe).
    """
    for resolve in _EMBED_REDIRECT_RESOLVERS:
        redirect_url = resolve(url, html)
        if redirect_url is not None:
            return redirect_url
    return None


def _extract_json_ld_description(html: str) -> str | None:
    """Pull a job posting's description out of a `schema.org JobPosting`
    block in a `<script type="application/ld+json">` tag, if one's present —
    the description field is itself an HTML string, so its tags are stripped
    the same way the visible-DOM fallback path strips them. Returns None if
    there's no such block, or it doesn't parse/match the expected shape.
    """
    for tag in BeautifulSoup(html, "html.parser").find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict) or data.get("@type") != "JobPosting":
            continue
        description = data.get("description")
        if isinstance(description, str) and description.strip():
            return BeautifulSoup(description, "html.parser").get_text(separator="\n", strip=True)
    return None


def _fetch_rendered_text(url: str, timeout: float) -> str | None:
    """Render `url` in headless Chromium and return its visible text, for
    pages whose content only exists after client-side JavaScript runs — the
    general fallback for ATS platforms with no server-rendered shortcut at
    all. Returns None (rather than raising) on any failure — a missing
    Playwright install, a missing browser binary, a navigation timeout — so a
    site this can't help with still falls through to the normal short-text
    error instead of a confusing, unrelated one.

    Checks every frame on the page, not just the top-level document — a
    third-party widget (an ATS embed, e.g.) is commonly rendered inside its
    own iframe, and `page.content()` alone only ever sees the main frame, so
    a frame holding the actual posting would otherwise be invisible here even
    though the browser genuinely rendered it.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(user_agent=_HEADERS["User-Agent"])
                page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
                frame_htmls = []
                for frame in page.frames:
                    try:
                        frame_htmls.append(frame.content())
                    except Exception:  # noqa: BLE001 - a detached/cross-origin
                        continue       # frame shouldn't abort the whole fetch
            finally:
                browser.close()
    except Exception:  # noqa: BLE001 - any render failure degrades to None, see above
        return None

    best_text = ""
    for html in frame_htmls:
        text = _extract_json_ld_description(html) or _visible_text(html)
        if len(text.strip()) > len(best_text.strip()):
            best_text = text
    return best_text or None