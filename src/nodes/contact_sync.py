"""Contact sync node — creates or updates a res.partner (contact) in Odoo after indexing.

Runs after the index node for contact-type documents (name cards, business cards).
Non-blocking: any Odoo failure is logged and the pipeline continues.

Logic:
  1. Skip non-contact doc types
  2. Dedup: search by email → mobile → name + company
  3. Create or update res.partner
"""

import logging
import os
import xmlrpc.client

from langsmith import traceable

from src.state import DocumentState, DocumentType

logger = logging.getLogger(__name__)

ODOO_URL = "https://c21net.odoo.com"
ODOO_DB = "c21net"
ODOO_USERNAME = "admin@c21net.com"
PARTNER_MODEL = "res.partner"


@traceable(name="contact_sync", run_type="chain")
def contact_sync(state: DocumentState) -> DocumentState:
    """Sync a name card document to Odoo res.partner. Non-blocking."""
    if state.document_type != DocumentType.CONTACT:
        state.odoo_sync_status = "skipped"
        return state

    api_key = os.environ.get("ODOO_API_KEY")
    if not api_key:
        logger.warning("contact_sync: ODOO_API_KEY not set, skipping '%s'", state.file_name)
        state.odoo_sync_status = "skipped"
        return state

    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_DB, ODOO_USERNAME, api_key, {})
        if not uid:
            raise ValueError("Odoo authentication failed — check ODOO_API_KEY")
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

        raw: dict = state.extracted.raw if state.extracted else {}
        vals = _build_partner_vals(raw)

        if not vals.get("name"):
            logger.info("contact_sync: no name extracted from '%s', skipping", state.file_name)
            state.odoo_sync_status = "skipped"
            return state

        partner_id = _find_existing(models, uid, api_key, raw)

        if partner_id:
            models.execute_kw(ODOO_DB, uid, api_key, PARTNER_MODEL, "write",
                              [[partner_id], vals])
            logger.info("contact_sync: updated partner %s for '%s'", partner_id, state.file_name)
        else:
            partner_id = models.execute_kw(ODOO_DB, uid, api_key, PARTNER_MODEL, "create", [vals])
            logger.info("contact_sync: created partner %s for '%s'", partner_id, state.file_name)

        state.odoo_record_id = str(partner_id)
        state.odoo_sync_status = "synced"

    except Exception as e:
        logger.error("contact_sync error for '%s': %s", state.file_name, e)
        state.odoo_sync_status = "error"
        # For xmlrpc Fault, extract last non-empty line (actual exception, not the traceback header)
        import xmlrpc.client as _xmlrpc
        if isinstance(e, _xmlrpc.Fault):
            last_line = next(
                (ln.strip() for ln in reversed(e.faultString.splitlines()) if ln.strip()),
                str(e),
            )
            state.odoo_error_detail = last_line
        else:
            state.odoo_error_detail = str(e)

    return state


def _build_partner_vals(raw: dict) -> dict:
    """Map extracted contact fields → Odoo res.partner field values.

    Only uses fields verified to exist and be writable on this Odoo instance.
    Fields not available as first-class fields (mobile, company) go into comment.
    """
    vals: dict = {}

    name = (raw.get("name_zh") or raw.get("name") or "").strip()
    if name:
        vals["name"] = name

    if raw.get("title"):
        vals["function"] = raw["title"].strip()

    # Primary phone: prefer landline, fall back to mobile
    phone = _first_phone(raw.get("phone") or raw.get("mobile") or "")
    if phone:
        vals["phone"] = phone

    if raw.get("email"):
        vals["email"] = raw["email"].strip().lower()

    if raw.get("address"):
        vals["street"] = raw["address"].strip()

    if raw.get("website"):
        vals["website"] = raw["website"].strip()

    # Fields not available as first-class on this Odoo instance go into notes
    notes = []
    company = (raw.get("company_zh") or raw.get("company") or "").strip()
    if company:
        notes.append(f"公司：{company}")
    mobile = _first_phone(raw.get("mobile") or "")
    if mobile and mobile != vals.get("phone"):
        notes.append(f"手機：{mobile}")
    name_en = (raw.get("name_en") or "").strip()
    if name_en and name_en != name:
        notes.append(f"English name: {name_en}")
    if notes:
        vals["comment"] = "<br/>".join(notes)

    return vals


def _first_phone(value: str) -> str:
    """Return the first phone number from a comma- or newline-separated string."""
    import re
    for part in re.split(r"[,\n]", value):
        part = part.strip()
        if part:
            return part
    return value.strip()


def _find_existing(models, uid: int, api_key: str, raw: dict) -> int | None:
    """Find an existing res.partner record.

    Dedup order: email (most reliable) → mobile → name + company.
    Returns partner ID or None.
    """
    def search(domain):
        try:
            found = models.execute_kw(ODOO_DB, uid, api_key, PARTNER_MODEL, "search", [domain], {"limit": 1})
            return found[0] if found else None
        except Exception as err:
            logger.warning("contact_sync: dedup search failed for domain %s: %s", domain, err)
            return None

    email = (raw.get("email") or "").strip().lower()
    if email:
        result = search([["email", "=", email]])
        if result:
            return result

    # Dedup by phone (mobile field does not exist on this Odoo instance)
    phone = _first_phone(raw.get("phone") or raw.get("mobile") or "")
    if phone:
        result = search([["phone", "=", phone]])
        if result:
            return result

    name = (raw.get("name_zh") or raw.get("name") or "").strip()
    if name:
        result = search([["name", "=", name]])
        if result:
            return result

    return None


