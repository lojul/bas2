"""Look up news/knowledge articles (knowledge.article) in Odoo. Real-time
direct query by keyword — simpler than a vector index, revisit only if article
volume grows large enough that keyword matching starts missing relevant ones.

Own XML-RPC client — same account as create_crm_lead.py / search_contacts.py,
deliberately not shared code.
"""

import logging
import re
import xmlrpc.client

from langchain_core.tools import tool

from core.config import ODOO_API_KEY, ODOO_DB, ODOO_URL, ODOO_USERNAME

ARTICLE_MODEL = "knowledge.article"
KNOWLEDGE_PARENT_ID = 39  # Marketing News — same folder knowledge_writer.py writes to

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html: str, max_len: int = 400) -> str:
    text = _TAG_RE.sub(" ", html or "")
    text = " ".join(text.split())
    return text[:max_len] + ("..." if len(text) > max_len else "")


def _format_article(a: dict) -> str:
    excerpt = _strip_html(a.get("body", ""))
    return f"- {a.get('name') or '(untitled)'} | {excerpt}"


@tool
def search_knowledge(query: str, top_k: int = 5) -> str:
    """Look up news or market knowledge articles by keyword.

    Use this when staff ask about recent property news, market updates, or
    reference material previously saved to the knowledge base. query can be
    one or more space-separated keywords (e.g. "觀塘 地產") — an article
    matching ANY of them is returned, since this is a substring match, not
    semantic search. Returns matching articles with a short excerpt, or a
    message if nothing matches.
    """
    if not ODOO_API_KEY:
        return "Odoo connection not configured (ODOO_API_KEY missing)."

    tokens = [t for t in query.split() if t.strip()] or [query]

    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_API_KEY, {})
        if not uid:
            return "Odoo authentication failed."
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

        # OR across (name ilike token) and (body ilike token) for every token,
        # so a multi-word query still matches an article containing any one of
        # them — a plain ilike on the whole phrase would rarely match real text.
        or_leaves = []
        for t in tokens:
            or_leaves.append(["name", "ilike", t])
            or_leaves.append(["body", "ilike", t])
        domain = [["parent_id", "=", KNOWLEDGE_PARENT_ID]]
        domain += (["|"] * (len(or_leaves) - 1) + or_leaves) if len(or_leaves) > 1 else or_leaves

        results = models.execute_kw(
            ODOO_DB, uid, ODOO_API_KEY, ARTICLE_MODEL, "search_read",
            [domain],
            {"fields": ["name", "body"], "limit": top_k},
        )
        if not results:
            return "No matching knowledge articles found."
        return "\n".join(_format_article(a) for a in results)
    except Exception as e:
        logging.exception("search_knowledge: failed")
        return f"Knowledge search failed: {str(e)[:150]}"
