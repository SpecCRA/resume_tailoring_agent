from unittest.mock import MagicMock, patch

import httpx
import pytest

from resume_agent.errors import ScrapingError
from resume_agent.tools import web_scraper
from resume_agent.tools.web_scraper import _fetch_rendered_text, fetch_job_text


@pytest.fixture(autouse=True)
def no_headless_render():
    """Every test's HTML fixtures are short (well under settings.min_jd_chars),
    so fetch_job_text would otherwise always escalate to a real headless
    browser launch — slow, non-deterministic, and dependent on real network
    access. Default the render fallback to "no improvement available" (as if
    Playwright weren't installed); tests that specifically exercise the
    escalation path override this themselves.
    """
    with patch("resume_agent.tools.web_scraper._fetch_rendered_text", return_value=None) as mock:
        yield mock


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


def test_fetch_job_text_redirects_an_embedded_ashby_widget_to_ashbys_own_page(respx_mock):
    # A career page embedding Ashby's widget renders only a shell client-side —
    # the board slug is findable in the embed script src even though the actual
    # posting text isn't present anywhere in this response.
    shell_html = (
        '<html><body><script src="https://jobs.ashbyhq.com/acmeco/embed?version=2">'
        "</script></body></html>"
    )
    respx_mock.get(
        "https://acme.example/careers?ashby_jid=abc-123"
    ).mock(return_value=httpx.Response(200, html=shell_html))

    ashby_html = "<html><body><p>Full job description text</p></body></html>"
    respx_mock.get("https://jobs.ashbyhq.com/acmeco/abc-123").mock(
        return_value=httpx.Response(200, html=ashby_html)
    )

    text = fetch_job_text("https://acme.example/careers?ashby_jid=abc-123")

    assert "Full job description text" in text


def test_fetch_job_text_leaves_non_ashby_urls_untouched(respx_mock):
    html = "<html><body><p>Job description text</p></body></html>"
    respx_mock.get("https://example.com/job?foo=bar").mock(
        return_value=httpx.Response(200, html=html)
    )

    text = fetch_job_text("https://example.com/job?foo=bar")

    assert "Job description text" in text


def test_fetch_job_text_leaves_ashby_jid_url_untouched_when_board_slug_not_found(respx_mock):
    # ashby_jid is present, but nothing on the page reveals the board slug —
    # nothing to redirect to, so the (likely-empty) shell text is returned as-is
    # rather than erroring, letting pipelines/tailor.py's length check catch it.
    html = "<html><body></body></html>"
    respx_mock.get("https://acme.example/careers?ashby_jid=abc-123").mock(
        return_value=httpx.Response(200, html=html)
    )

    text = fetch_job_text("https://acme.example/careers?ashby_jid=abc-123")

    assert text == ""


def test_fetch_job_text_extracts_description_from_json_ld_job_posting(respx_mock):
    # Reproduces the actual reported bug: some ATS-hosted pages (e.g. Ashby's
    # own jobs.ashbyhq.com pages) render the posting ONLY inside a JSON-LD
    # JobPosting block for Google-for-Jobs indexing — nothing is in the
    # visible DOM at all, so the boilerplate-stripping fallback would return
    # next to nothing if this extraction didn't run first.
    html = """<html><body>
<script type="application/ld+json">
{"@context": "https://schema.org/", "@type": "JobPosting",
 "title": "Analytics Engineer",
 "description": "<p><strong>Our Team</strong></p><p>Build things.</p>"}
</script>
</body></html>"""
    respx_mock.get("https://jobs.ashbyhq.com/acmeco/abc-123").mock(
        return_value=httpx.Response(200, html=html)
    )

    text = fetch_job_text("https://jobs.ashbyhq.com/acmeco/abc-123")

    assert "Our Team" in text
    assert "Build things." in text
    assert "<p>" not in text


def test_fetch_job_text_resolves_ashby_embed_then_extracts_json_ld(respx_mock):
    """End-to-end reproduction of the original bug report: a Squarespace
    career page embedding an Ashby widget, redirected to Ashby's hosted page,
    whose content lives only in JSON-LD."""
    shell_html = (
        '<html><body><script src="https://jobs.ashbyhq.com/dandelionhealth/embed?version=2">'
        "</script></body></html>"
    )
    respx_mock.get(
        "https://dandelionhealth.ai/careers?ashby_jid=3070b88a-c42c-4136-bb87-9eb950efd154"
    ).mock(return_value=httpx.Response(200, html=shell_html))

    ashby_html = """<html><body>
<script type="application/ld+json">
{"@type": "JobPosting", "title": "Analytics Engineer",
 "description": "<p>Full posting content here.</p>"}
</script>
</body></html>"""
    respx_mock.get(
        "https://jobs.ashbyhq.com/dandelionhealth/3070b88a-c42c-4136-bb87-9eb950efd154"
    ).mock(return_value=httpx.Response(200, html=ashby_html))

    text = fetch_job_text(
        "https://dandelionhealth.ai/careers?ashby_jid=3070b88a-c42c-4136-bb87-9eb950efd154"
    )

    assert "Full posting content here." in text


def test_fetch_job_text_falls_back_to_visible_dom_when_json_ld_has_no_job_posting(respx_mock):
    html = (
        '<html><body><script type="application/ld+json">{"@type": "WebSite"}</script>'
        "<p>Job description text</p></body></html>"
    )
    respx_mock.get("https://example.com/job").mock(return_value=httpx.Response(200, html=html))

    text = fetch_job_text("https://example.com/job")

    assert "Job description text" in text


def test_fetch_job_text_escalates_to_headless_render_when_fast_path_is_too_short(
    respx_mock, no_headless_render
):
    # The fast path gets almost nothing (a pure client-rendered SPA shell) —
    # fetch_job_text should escalate to the (mocked) headless render and use
    # its result instead, since it's longer/actually has content.
    shell_html = "<html><body><div id=\"app\"></div></body></html>"
    respx_mock.get("https://portal.example/job/1").mock(
        return_value=httpx.Response(200, html=shell_html)
    )
    no_headless_render.return_value = "Full rendered job description text " * 10

    text = fetch_job_text("https://portal.example/job/1")

    assert "Full rendered job description text" in text


def test_fetch_job_text_does_not_escalate_when_fast_path_already_has_enough_text(
    respx_mock, no_headless_render
):
    from resume_agent.config import settings

    html = f"<html><body><p>{'Real job content. ' * 20}</p></body></html>"
    assert len(html) >= settings.min_jd_chars
    respx_mock.get("https://example.com/job").mock(return_value=httpx.Response(200, html=html))

    fetch_job_text("https://example.com/job")

    no_headless_render.assert_not_called()


def test_fetch_job_text_keeps_fast_path_text_when_render_fallback_returns_none(
    respx_mock, no_headless_render
):
    # _fetch_rendered_text returning None (Playwright unavailable, navigation
    # failure, etc.) must not crash fetch_job_text — the short fast-path text
    # is returned as-is, letting pipelines/tailor.py's length gate handle it.
    html = "<html><body><p>short</p></body></html>"
    respx_mock.get("https://example.com/job").mock(return_value=httpx.Response(200, html=html))

    text = fetch_job_text("https://example.com/job")

    assert text == "short"


def test_resolve_known_embed_redirect_tries_resolvers_in_order(monkeypatch):
    monkeypatch.setattr(
        web_scraper,
        "_EMBED_REDIRECT_RESOLVERS",
        [lambda url, html: None, lambda url, html: "https://redirected.example/posting"],
    )

    result = web_scraper._resolve_known_embed_redirect("https://x.example", "<html></html>")

    assert result == "https://redirected.example/posting"


def test_resolve_known_embed_redirect_returns_none_when_nothing_matches(monkeypatch):
    monkeypatch.setattr(web_scraper, "_EMBED_REDIRECT_RESOLVERS", [lambda url, html: None])

    result = web_scraper._resolve_known_embed_redirect("https://x.example", "<html></html>")

    assert result is None


def _mock_playwright_page(frame_contents: list[str | Exception]) -> MagicMock:
    """Build a mock sync_playwright() context manager whose rendered page
    exposes one mock frame per entry in `frame_contents` — a string frame
    returns that content, an Exception instance makes that frame's
    `.content()` raise it (simulating a detached/cross-origin frame)."""
    page = MagicMock()
    page.frames = []
    for content in frame_contents:
        frame = MagicMock()
        if isinstance(content, Exception):
            frame.content.side_effect = content
        else:
            frame.content.return_value = content
        page.frames.append(frame)

    browser = MagicMock()
    browser.new_page.return_value = page

    p = MagicMock()
    p.chromium.launch.return_value = browser

    pw_context_manager = MagicMock()
    pw_context_manager.__enter__.return_value = p
    pw_context_manager.__exit__.return_value = False
    return pw_context_manager


def test_fetch_rendered_text_picks_whichever_frame_has_the_most_text():
    # Reproduces the real Ashby case: the main page is near-empty, and the
    # actual posting lives in a separate (e.g. iframed widget) frame.
    main_frame_html = "<html><body>Careers — Acme</body></html>"
    embed_frame_html = "<html><body><p>" + "Full posting content. " * 20 + "</p></body></html>"

    pw_context_manager = _mock_playwright_page([main_frame_html, embed_frame_html])

    with patch("playwright.sync_api.sync_playwright", return_value=pw_context_manager):
        text = _fetch_rendered_text("https://example.com/job", 15.0)

    assert text is not None
    assert "Full posting content." in text
    assert "Careers — Acme" not in text


def test_fetch_rendered_text_skips_a_frame_whose_content_call_raises():
    good_frame_html = "<html><body><p>" + "Usable posting content. " * 20 + "</p></body></html>"
    pw_context_manager = _mock_playwright_page([Exception("frame detached"), good_frame_html])

    with patch("playwright.sync_api.sync_playwright", return_value=pw_context_manager):
        text = _fetch_rendered_text("https://example.com/job", 15.0)

    assert text is not None
    assert "Usable posting content." in text


def test_fetch_rendered_text_returns_none_when_playwright_is_not_installed():
    with patch.dict("sys.modules", {"playwright.sync_api": None}):
        text = _fetch_rendered_text("https://example.com/job", 15.0)

    assert text is None


def test_fetch_rendered_text_returns_none_on_navigation_failure():
    pw_context_manager = _mock_playwright_page([])
    p = pw_context_manager.__enter__.return_value
    page = p.chromium.launch.return_value.new_page.return_value
    page.goto.side_effect = Exception("navigation timeout")

    with patch("playwright.sync_api.sync_playwright", return_value=pw_context_manager):
        text = _fetch_rendered_text("https://example.com/job", 15.0)

    assert text is None
