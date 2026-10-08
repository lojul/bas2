"""Fetch clean article content from URLs using Tavily Extract API.

Used by the classify node to enrich short OCR text that contains URLs —
so the LLM sees the actual article content, not just the link.
"""

import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

# Printable-ASCII only (not \S+) — \S+ also matches CJK characters appended
# directly with no separator (e.g. "http://on.cc東網", a source citation like
# "on.cc東網" that isn't a real link at all, just text starting with "http://").
# Real URLs don't contain raw literal CJK, so stopping at ASCII avoids treating
# citation text as a fetchable/linkable URL. Confirmed bug 2026-08-04.
_URL_PATTERN = re.compile(r"https?://[!-~]+")


def extract_urls(text: str) -> list[str]:
    """Return all http/https URLs found in text."""
    return _URL_PATTERN.findall(text)


def _get_with_redirects(url: str) -> tuple[str, str]:
    """GET a URL following redirects, returning (final_url, html_text).

    Uses GET, not HEAD — share.google's redirect handler only completes its
    full (2-hop) redirect chain to the real article on GET. A HEAD request
    stops after 1 hop, landing on a Google interstitial page that needs JS to
    go further. Confirmed via direct testing 2026-08-04.
    """
    with httpx.Client(
        timeout=10,
        follow_redirects=True,
        max_redirects=5,
        headers={"User-Agent": "Mozilla/5.0"},
    ) as client:
        resp = client.get(url)
        return str(resp.url), resp.text


def resolve_redirect(url: str) -> str:
    """Follow HTTP redirects and return the final canonical URL.

    Handles share.google, bit.ly, and other shorteners that redirect
    to the actual article URL.
    """
    try:
        final, _ = _get_with_redirects(url)
        if final != url:
            logger.info("URL resolved: %s → %s", url, final)
        return final
    except Exception as e:
        logger.debug("Redirect resolution failed for %s: %s", url, e)
        return url


_ARTICLE_TAG_RE = re.compile(r"<article\b[^>]*>(.*?)</article>", re.S | re.I)
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_BLANK_LINES_RE = re.compile(r"\n\s*\n+")


def _extract_article_tag_text(html: str) -> str | None:
    """Pull the <article> tag's inner text out of raw HTML, if present.

    A direct, dependency-free extraction — no external service involved, so
    it isn't subject to a site's bot/crawler defenses the way a third-party
    extraction API can be (confirmed 2026-08-04: Tavily's Extract API got a
    bot-wall placeholder page from etnet.com.hk on a URL that a plain GET
    with a normal User-Agent fetched the real article from just fine).
    """
    m = _ARTICLE_TAG_RE.search(html)
    if not m:
        return None
    inner = _SCRIPT_STYLE_RE.sub("", m.group(1))
    text = _TAG_RE.sub("\n", inner)
    text = _BLANK_LINES_RE.sub("\n\n", text).strip()
    return text or None


def _fetch_via_tavily(url: str) -> str | None:
    """Fetch clean article text from a URL via Tavily Extract."""
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        logger.debug("TAVILY_API_KEY not set — skipping Tavily fetch for %s", url)
        return None
    try:
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                "https://api.tavily.com/extract",
                json={"urls": [url], "api_key": api_key},
                timeout=20,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if results:
                content = results[0].get("raw_content") or results[0].get("content") or ""
                if content.strip():
                    logger.info("Tavily fetch OK: %s (%d chars)", url, len(content))
                    return content.strip()
    except Exception as e:
        logger.warning("Tavily fetch failed for %s: %s", url, e)
    return None


def fetch_url_content(url: str, min_direct_chars: int = 200) -> str | None:
    """Fetch clean article text from a URL.

    Tries a direct fetch + <article> tag extraction first (reliable, no
    external dependency, not subject to a destination site's bot defenses
    against known crawler services). Falls back to Tavily Extract if the
    direct fetch doesn't find a usable <article> tag (e.g. JS-rendered
    sites with no server-side article markup).
    """
    try:
        final_url, html = _get_with_redirects(url)
    except Exception as e:
        logger.debug("Direct fetch failed for %s: %s", url, e)
        final_url, html = url, ""

    if html:
        direct = _extract_article_tag_text(html)
        if direct and len(direct) >= min_direct_chars:
            logger.info("Direct fetch OK: %s (%d chars)", final_url, len(direct))
            return direct

    return _fetch_via_tavily(final_url)


def enrich_with_url_content(text: str, max_chars: int = 8000) -> str:
    """If text is short and contains URLs, fetch and append their content.

    Only enriches when the text is URL-dominant (< 300 chars) to avoid
    fetching unnecessarily when the document already has real content.
    Fetches at most 2 URLs to keep latency reasonable.
    """
    if len(text.strip()) >= 300:
        return text  # already has substantive content

    urls = extract_urls(text)
    if not urls:
        return text

    fetched_parts: list[str] = []
    for url in urls[:2]:
        content = fetch_url_content(url)
        if content:
            fetched_parts.append(
                f"[從連結擷取的內容 / Content fetched from {url}]\n{content[:max_chars]}"
            )

    if not fetched_parts:
        return text

    return text + "\n\n" + "\n\n".join(fetched_parts)
