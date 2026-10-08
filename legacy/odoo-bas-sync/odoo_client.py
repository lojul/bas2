"""Thin XML-RPC client for reading/writing x_c21_listing records in Odoo.

Same connection pattern as document-processor's src/nodes/odoo_sync.py — different
codebase, but talking to the same Odoo instance/model.
"""

import os
import xmlrpc.client

ODOO_URL = os.environ.get("ODOO_URL", "https://c21net.odoo.com")
ODOO_DB = os.environ.get("ODOO_DB", "c21net")
ODOO_USERNAME = os.environ.get("ODOO_USERNAME", "admin@c21net.com")

MODEL = "x_c21_listing"

# Fields pulled per record.
FIELDS = [
    "id",
    "x_name",
    "x_c21_address",
    "x_c21_district",
    "x_c21_property_type",
    "x_c21_rent_net",
    "x_c21_size_sqft",
    "x_c21_contact_name",
    "x_c21_contact_phone",
    "x_c21_floor_unit",
    "x_c21_date_received",
    "x_c21_ocr_text",
    "x_c21_doc_url",
]


class OdooClient:
    def __init__(self) -> None:
        api_key = os.environ.get("ODOO_API_KEY")
        if not api_key:
            raise ValueError("ODOO_API_KEY not set")

        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_DB, ODOO_USERNAME, api_key, {})
        if not uid:
            raise ValueError("Odoo authentication failed — check ODOO_API_KEY")

        self._uid = uid
        self._api_key = api_key
        self._models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

    def _execute(self, model: str, method: str, *args, **kwargs):
        return self._models.execute_kw(
            ODOO_DB, self._uid, self._api_key, model, method, list(args), kwargs
        )

    def fetch_pending(self) -> list[dict]:
        """Records where x_c21_published=False — new or edited since last sync."""
        return self._execute(
            MODEL, "search_read",
            [["x_c21_published", "=", False]],
            fields=FIELDS,
        )

    def mark_published(self, record_id: int) -> None:
        self._execute(MODEL, "write", [record_id], {"x_c21_published": True})
