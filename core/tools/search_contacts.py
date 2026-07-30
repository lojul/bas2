"""Look up contacts (res.partner) in Odoo. Real-time direct query, no vector
index — exact/fuzzy lookups by name, phone, email, or company are a better fit
for a direct query than semantic search, and always reflect live Odoo data.

Own XML-RPC client — same account as create_crm_lead.py, deliberately not
shared code (see core/tools/create_crm_lead.py for the reasoning).
"""

import logging
import xmlrpc.client

from langchain_core.tools import tool

from core.config import ODOO_API_KEY, ODOO_DB, ODOO_URL, ODOO_USERNAME

PARTNER_MODEL = "res.partner"


def _format_contact(c: dict) -> str:
    parts = [f"- {c.get('name') or '(no name)'}"]
    if c.get("function"):
        parts.append(f"Title: {c['function']}")
    if c.get("phone"):
        parts.append(f"Phone: {c['phone']}")
    if c.get("email"):
        parts.append(f"Email: {c['email']}")
    if c.get("street"):
        parts.append(f"Address: {c['street']}")
    if c.get("comment"):
        parts.append(f"Notes: {c['comment']}")
    return " | ".join(parts)


@tool
def search_contacts(query: str, top_k: int = 5) -> str:
    """Look up a contact in Odoo by name, phone, email, or company.

    Use this when staff ask whether we have contact info for someone, or ask
    to look up a name/phone number/email. Returns matching contacts, or a
    message if nothing matches.
    """
    if not ODOO_API_KEY:
        return "Odoo connection not configured (ODOO_API_KEY missing)."

    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_API_KEY, {})
        if not uid:
            return "Odoo authentication failed."
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

        domain = [
            "|", "|", "|",
            ["name", "ilike", query],
            ["phone", "ilike", query],
            ["email", "ilike", query],
            ["comment", "ilike", query],
        ]
        results = models.execute_kw(
            ODOO_DB, uid, ODOO_API_KEY, PARTNER_MODEL, "search_read",
            [domain],
            {"fields": ["name", "function", "phone", "email", "street", "comment"], "limit": top_k},
        )
        if not results:
            return "No matching contacts found."
        return "\n".join(_format_contact(c) for c in results)
    except Exception as e:
        logging.exception("search_contacts: failed")
        return f"Contact search failed: {str(e)[:150]}"
