"""Fetch clean article content from URLs using Tavily Extract API.

Used by the classify node to enrich short OCR text that contains URLs —
so the LLM sees the actual article content, not just the link.
"""

import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

_URL_PATTERN = re.compile(r"https?://\S+")


def extract_urls(text: str) -> list[str]:
    """Return all http/https URLs found in text."""
    return _URL_PATTERN.findall(text)


def resolve_redirect(url: str) -> str:
    """Follow HTTP redirects and return the final canonical URL.

    Handles share.google, bit.ly, and other shorteners that redirect
    to the actual article URL that Tavily can extract.
    """
    # share.google and similar require a browser session — their redirects end at
    # Google's own page, which Tavily can't extract. Skip redirect resolution for
    # these domains and let Tavily attempt the original URL directly.
    _SKIP_REDIRECT_DOMAINS = ("share.google", "accounts.google.com")
    if any(d in url for d in _SKIP_REDIRECT_DOMAINS):
        return url

    try:
        with httpx.Client(
            timeout=8,
            follow_redirects=True,
            max_redirects=5,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            resp = client.head(url)
            final = str(resp.url)
            if final != url:
                logger.info("URL resolved: %s → %s", url, final)
            return final
    except Exception as e:
        logger.debug("Redirect resolution failed for %s: %s", url, e)
        return url


def fetch_url_content(url: str) -> str | None:
    """Fetch clean article text from a URL via Tavily Extract.

    Follows redirects first (handles share.google, bit.ly, etc.)
    then tries Tavily Extract on the final URL.
    Returns the raw article content, or None if the fetch fails.
    """
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        logger.debug("TAVILY_API_KEY not set — skipping URL fetch for %s", url)
        return None

    # Follow redirects so Tavily sees the actual article URL
    final_url = resolve_redirect(url)

    try:
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                "https://api.tavily.com/extract",
                json={"urls": [final_url], "api_key": api_key},
                timeout=20,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if results:
                content = results[0].get("raw_content") or results[0].get("content") or ""
                if content.strip():
                    logger.info("URL fetch OK: %s (%d chars)", final_url, len(content))
                    return content.strip()
    except Exception as e:
        logger.warning("URL fetch failed for %s: %s", final_url, e)
    return None


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
