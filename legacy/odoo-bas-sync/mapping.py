"""Odoo x_c21_listing record -> BAS properties-index document.

Field mapping per project-odoo-to-bas-sync memory, Part 3. Kept as a pure function
(no I/O) so it's easy to unit test independent of Odoo/Azure connectivity.
"""

from datetime import datetime, timezone

# Odoo stores district as a snake_case selection key (e.g. "kwun_tong").
# BAS expects a readable English label. Reverse of odoo_sync.py's DISTRICT_MAP,
# written out explicitly rather than derived (that map's keys are Chinese/English
# text -> snake_case; several English variants collapse onto one snake_case value).
DISTRICT_LABELS: dict[str, str] = {
    "kwun_tong": "Kwun Tong",
    "kwai_fong": "Kwai Fong",
    "kwai_chung": "Kwai Chung",
    "tsuen_wan": "Tsuen Wan",
    "mong_kok": "Mong Kok",
    "tsim_sha_tsui": "Tsim Sha Tsui",
    "causeway_bay": "Causeway Bay",
    "wan_chai": "Wan Chai",
    "central": "Central",
    "sheung_wan": "Sheung Wan",
    "cheung_sha_wan": "Cheung Sha Wan",
    "kowloon_bay": "Kowloon Bay",
    "san_po_kong": "San Po Kong",
}


def _iso_date(raw: str | None) -> str | None:
    """Odoo date string ('2026-07-15') -> DateTimeOffset ISO string BAS expects."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def build_content(record: dict) -> str:
    """Real OCR text when available (Part 5 target), else a thin structured fallback."""
    ocr_text = (record.get("x_c21_ocr_text") or "").strip()
    if ocr_text:
        return ocr_text

    parts = [
        record.get("x_name"),
        record.get("x_c21_address"),
        record.get("x_c21_floor_unit"),
    ]
    return " / ".join(p for p in parts if p)


def map_listing(record: dict) -> dict:
    """Build the BAS properties-index document for one Odoo x_c21_listing record.

    Does not include contentVector — the caller embeds build_content() separately
    and adds it, since embedding requires a network call this function shouldn't make.
    """
    record_id = record["id"]

    return {
        "id": f"odoo-listing-{record_id}",
        "address": record.get("x_c21_address") or record.get("x_name") or "",
        "district": DISTRICT_LABELS.get(record.get("x_c21_district") or "", ""),
        "propertyType": record.get("x_c21_property_type") or "",
        "price": record.get("x_c21_rent_net") or None,
        "area_sqft": record.get("x_c21_size_sqft") or None,
        "agentName": record.get("x_c21_contact_name") or "",
        "listingDate": _iso_date(record.get("x_c21_date_received")),
        "sourceWebUrl": record.get("x_c21_doc_url") or "",
        # Synthetic, non-empty — only needs to be truthy to pass BAS's
        # build_related_media() gate (Part 4). Reuses the same id as above.
        "sourceBlob": f"odoo-listing-{record_id}",
        "docType": "property_listing",
        # No Odoo field for this yet (Part 6 #4) — accept the default until one exists.
        "transactionType": "rent",
        "content": build_content(record),
    }
