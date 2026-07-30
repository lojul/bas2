"""Create a CRM lead in Odoo. Own XML-RPC client — deliberately not shared with
document-processor's odoo_sync.py or assistant.py, per the "separate codeline,
no shared imports" requirement. Same Odoo account, independent connection.
"""

import logging
import xmlrpc.client

from langchain_core.tools import tool

from core.config import ODOO_API_KEY, ODOO_DB, ODOO_URL, ODOO_USERNAME

# utm.source id 16 = "Chatbot" (generic, already exists in Odoo — distinct from
# id 20 "WhatsApp" used by the document-intake assistant and id 21 "BAS Teams
# Agent" used by BAS's own bot). Channel is recorded in the lead description
# instead of creating a new UTM source per channel.
CHATBOT_SOURCE_ID = 16
SALES_TEAM_ID = 1


@tool
def create_crm_lead(contact_name: str, phone: str = "", notes: str = "", channel: str = "") -> str:
    """Create a CRM lead in Odoo when a user expresses interest in a property
    or asks to be contacted by an agent.

    contact_name: the client's name (required).
    phone: client's phone number.
    notes: free-text summary of what they're interested in (property, terms, etc).
    channel: which channel this came from (e.g. "slack") — recorded for traceability.
    """
    if not ODOO_API_KEY:
        return "Odoo connection not configured (ODOO_API_KEY missing)."

    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_API_KEY, {})
        if not uid:
            return "Odoo authentication failed."
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

        description_parts = []
        if channel:
            description_parts.append(f"Channel: {channel}")
        if notes:
            description_parts.append(notes)
        description = "\n".join(description_parts)

        vals: dict = {
            "name": f"Property Chatbot Inquiry — {contact_name}",
            "partner_name": contact_name,
            "contact_name": contact_name,
            "team_id": SALES_TEAM_ID,
            "source_id": CHATBOT_SOURCE_ID,
            "type": "lead",
        }
        if phone:
            vals["phone"] = phone
        if description:
            vals["description"] = description

        lead_id = models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, "crm.lead", "create", [vals])
        logging.info("create_crm_lead: created lead %s for %s", lead_id, contact_name)
        return f"Lead created successfully (Odoo CRM lead ID: {lead_id})."
    except Exception as e:
        logging.exception("create_crm_lead: failed")
        return f"Failed to create lead: {str(e)[:150]}"
