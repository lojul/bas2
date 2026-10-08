"""Web search via Tavily — for questions the internal data can't answer:
general market trends, news, government policy, anything not already in
properties-index/Odoo. Same role Tavily played in the old chatbot.py.
"""

import logging

import httpx
from langchain_core.tools import tool

from core.config import TAVILY_API_KEY


def _format_result(r: dict) -> str:
    snippet = (r.get("content") or "")[:300]
    return f"- {r.get('title') or '(no title)'} | {r.get('url') or ''} | {snippet}"


@tool
def web_search(query: str, max_results: int = 3) -> str:
    """Search the web for general Hong Kong commercial property market
    information — trends, news, policy changes — not already covered by
    search_properties or search_knowledge. Use this only when staff ask
    about the broader market rather than a specific listing or a saved
    knowledge article.
    """
    if not TAVILY_API_KEY:
        return "Web search not configured (TAVILY_API_KEY missing)."

    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": f"{query} Hong Kong commercial property real estate",
                "max_results": max_results,
            },
            timeout=20,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return "No web results found."
        return "\n".join(_format_result(r) for r in results[:max_results])
    except Exception as e:
        logging.exception("web_search: failed")
        return f"Web search failed: {str(e)[:150]}"
