"""Create a CRM lead in Odoo. Own XML-RPC client — deliberately not shared with
document-processor's odoo_sync.py or assistant.py, per the "separate codeline,
no shared imports" requirement. Same Odoo account, independent connection.
"""

from langchain_core.tools import tool

# TODO: real implementation — xmlrpc.client against crm.lead, same field
# mapping assistant.py already uses (name, contact_name, email_from, phone,
# partner_name, description, source_id, type='lead').


@tool
def create_crm_lead(contact_name: str, phone: str = "", notes: str = "") -> str:
    """Create a CRM lead in Odoo when a user expresses interest in a property
    or asks to be contacted by an agent.

    Not yet implemented — scaffold only.
    """
    return "create_crm_lead: not yet implemented"
