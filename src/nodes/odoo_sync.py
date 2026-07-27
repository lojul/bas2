"""Odoo sync node — creates or updates a C21 放盤管理 (x_c21_listing) record after indexing.

Runs after the index node. Fully non-blocking: any Odoo failure is logged and the
pipeline continues. Document processing is never affected by Odoo availability.

Logic:
  1. Skip non-property doc types (news, contact)
  2. Upload the PDF to Odoo Documents (folder "Property Listings", ID 58)
  3. listing/pitching_deck → one record; listing_list → ONE RECORD PER UNIT
  4. If state.odoo_record_id is set → update that record (reprocessing path)
     Otherwise → search by x_name, then x_c21_address → update if found, else create
  5. Patch Azure AI Search doc with odoo_record_id + odoo_sync_status

Required env var: ODOO_API_KEY
"""

import os
import re
import base64
import logging
import xmlrpc.client
from datetime import date
from typing import Any

import httpx
from langsmith import traceable

from src.state import DocumentState, DocumentType
from src.utils.als_lookup import lookup_building

logger = logging.getLogger(__name__)

ODOO_URL = "https://c21net.odoo.com"
ODOO_DB = "c21net"
ODOO_USERNAME = "admin@c21net.com"
ODOO_MODEL = "x_c21_listing"
BUILDING_MODEL = "x_c21_building"
DOCUMENTS_FOLDER_ID = 58  # "Property Listings" folder

SYNCABLE_TYPES = {DocumentType.LISTING, DocumentType.PITCHING_DECK, DocumentType.LISTING_LIST}

DISTRICT_MAP: dict[str, str] = {
    "觀塘": "kwun_tong", "kwun tong": "kwun_tong", "kwun_tong": "kwun_tong",
    "葵芳": "kwai_fong", "kwai fong": "kwai_fong",
    "葵涌": "kwai_chung", "kwai chung": "kwai_chung",
    "荃灣": "tsuen_wan", "tsuen wan": "tsuen_wan",
    "旺角": "mong_kok", "mong kok": "mong_kok",
    "尖沙咀": "tsim_sha_tsui", "tsim sha tsui": "tsim_sha_tsui",
    "銅鑼灣": "causeway_bay", "causeway bay": "causeway_bay",
    "灣仔": "wan_chai", "wan chai": "wan_chai",
    "中環": "central", "central": "central",
    "上環": "sheung_wan", "sheung wan": "sheung_wan",
    "長沙灣": "cheung_sha_wan", "cheung sha wan": "cheung_sha_wan",
    "九龍灣": "kowloon_bay", "kowloon bay": "kowloon_bay",
    "新蒲崗": "san_po_kong", "san po kong": "san_po_kong",
}

PROPERTY_TYPE_MAP: dict[str, str] = {
    "地舖": "ground_shop", "ground shop": "ground_shop", "ground_shop": "ground_shop",
    "寫字樓": "office", "office": "office",
    "工廈": "industrial", "industrial": "industrial",
    "商舖": "retail", "retail": "retail",
    "住宅": "residential", "residential": "residential",
}


@traceable(name="odoo_sync", run_type="chain")
def odoo_sync(state: DocumentState) -> DocumentState:
    """Sync processed document to Odoo x_c21_listing. Non-blocking."""
    # Skip doc types that don't map to Odoo property listings
    if state.document_type not in SYNCABLE_TYPES:
        state.odoo_sync_status = "skipped"
        logger.info("Odoo sync: skipping %s (type=%s)", state.file_name, state.document_type)
        return state

    api_key = os.environ.get("ODOO_API_KEY")
    if not api_key:
        logger.warning("Odoo sync: ODOO_API_KEY not set, skipping for '%s'", state.file_name)
        state.odoo_sync_status = "skipped"
        return state

    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_DB, ODOO_USERNAME, api_key, {})
        if not uid:
            raise ValueError("Odoo authentication failed — check ODOO_API_KEY")
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

        doc_url = _upload_to_documents(models, uid, api_key, state)
        state.file_bytes = None  # bytes no longer needed after Documents upload

        if doc_url:
            state.odoo_doc_url = doc_url

        # Resolve (or create) the parent building record before syncing units
        raw: dict = state.extracted.raw if state.extracted else {}
        building_id = _get_or_create_building(models, uid, api_key, raw)

        if state.document_type == DocumentType.LISTING_LIST:
            # Multi-property file: one Odoo record per unit
            ids = _sync_units(models, uid, api_key, state, doc_url, building_id)
            if not ids:
                state.odoo_sync_status = "skipped"
                logger.info("Odoo sync: no units extracted for '%s', skipping", state.file_name)
                return state
            state.odoo_record_id = ",".join(map(str, ids))
            state.odoo_sync_status = "synced"
            _patch_search_doc(state.index_id, state.odoo_record_id, "synced", doc_url)
            logger.info(
                "Odoo sync complete for '%s': %d unit records %s",
                state.file_name, len(ids), ids,
            )
            return state

        vals = _map_fields(state, doc_url, building_id)
        odoo_id = _create_or_update(models, uid, api_key, state.odoo_record_id, vals)

        state.odoo_record_id = str(odoo_id)
        state.odoo_sync_status = "synced"
        _patch_search_doc(state.index_id, str(odoo_id), "synced", doc_url)

        logger.info(
            "Odoo sync complete for '%s': record ID %s, doc_url=%s",
            state.file_name, odoo_id, doc_url or "none",
        )

    except Exception as e:
        logger.error("Odoo sync error for '%s': %s", state.file_name, e)
        state.odoo_sync_status = "error"
        state.odoo_error_detail = str(e)
        _patch_search_doc(state.index_id, state.odoo_record_id or "", "error", None)

    state.file_bytes = None
    return state


# ---------------------------------------------------------------------------
# Odoo Documents upload
# ---------------------------------------------------------------------------

def _upload_to_documents(models: Any, uid: int, api_key: str, state: DocumentState) -> str | None:
    """Upload PDF to Odoo Documents folder 58 and return the shareable URL."""
    pdf_bytes = state.file_bytes
    if not pdf_bytes and state.blob_url:
        try:
            with httpx.Client(timeout=60) as client:
                resp = client.get(state.blob_url)
                resp.raise_for_status()
                pdf_bytes = resp.content
        except Exception as e:
            logger.warning("Odoo sync: PDF download failed, skipping Documents upload: %s", e)
            return None

    if not pdf_bytes:
        logger.info("Odoo sync: no PDF bytes available for '%s', skipping Documents upload", state.file_name)
        return None

    datas = base64.b64encode(pdf_bytes).decode()

    # Reuse existing document if already in folder
    existing = models.execute_kw(
        ODOO_DB, uid, api_key, "documents.document", "search",
        [[["name", "=", state.file_name], ["folder_id", "=", DOCUMENTS_FOLDER_ID]]],
    )
    if existing:
        doc_id = existing[0]
        models.execute_kw(ODOO_DB, uid, api_key, "documents.document", "write",
                          [[doc_id], {"datas": datas}])
    else:
        doc_id = models.execute_kw(ODOO_DB, uid, api_key, "documents.document", "create", [{
            "name": state.file_name,
            "datas": datas,
            "folder_id": DOCUMENTS_FOLDER_ID,
            "mimetype": "application/pdf",
        }])

    doc_data = models.execute_kw(
        ODOO_DB, uid, api_key, "documents.document", "read",
        [[doc_id], ["access_token"]],
    )
    token = doc_data[0].get("access_token") if doc_data else None
    return f"{ODOO_URL}/odoo/documents/{token}" if token else None


# ---------------------------------------------------------------------------
# Building parent — find or create
# ---------------------------------------------------------------------------

def _get_or_create_building(models: Any, uid: int, api_key: str, raw: dict) -> int | None:
    """Return Odoo x_c21_building record ID, creating it if needed.

    Resolution order:
    1. ALS lookup on building name → canonical name + GeoAddress dedup key
    2. Search Odoo by ALS GeoAddress (exact, permanent key)
    3. Search Odoo by building name (ilike, fallback when ALS misses)
    4. Create new building record (with needs_review=True if ALS missed)
    """
    building_name = (raw.get("building_name") or raw.get("project_name") or "").strip()
    if not building_name:
        return None

    try:
        # ALS lookup for canonical data + dedup key
        als = lookup_building(building_name)

        if als and als.geo_id:
            # Search by stable GeoAddress ID first
            found = models.execute_kw(
                ODOO_DB, uid, api_key, BUILDING_MODEL, "search",
                [[["x_als_geo_id", "=", als.geo_id]]],
            )
            if found:
                return found[0]

        # Fallback: search by name (handles ALS misses + previously created records)
        search_name = als.name_zh if als else building_name
        found = models.execute_kw(
            ODOO_DB, uid, api_key, BUILDING_MODEL, "search",
            [[["x_name", "ilike", search_name]]],
        )
        if found:
            return found[0]

        # Create new building record
        vals: dict = {
            "x_name": als.name_zh if als else building_name,
            "x_needs_review": als is None,  # flag for manual review when ALS couldn't confirm
        }
        if als:
            vals["x_name_en"] = als.name_en
            vals["x_address"] = als.address_zh
            vals["x_als_geo_id"] = als.geo_id
            if als.lat is not None:
                vals["x_lat"] = als.lat
            if als.lng is not None:
                vals["x_lng"] = als.lng
            # Prefer AI-extracted district (sub-district level) over ALS DC district
            ai_district = _map_district(raw.get("district") or raw.get("area") or "")
            vals["x_district"] = ai_district or als.district_odoo
        else:
            # ALS unavailable — use AI-extracted data only
            ai_district = _map_district(raw.get("district") or raw.get("area") or "")
            if ai_district:
                vals["x_district"] = ai_district
            address = raw.get("address")
            if address:
                vals["x_address"] = address

        type_key = _map_property_type(raw.get("property_type") or "")
        if type_key:
            vals["x_property_type"] = type_key

        building_id = models.execute_kw(ODOO_DB, uid, api_key, BUILDING_MODEL, "create", [vals])
        logger.info(
            "Created building '%s' (id=%s, als=%s, needs_review=%s)",
            vals["x_name"], building_id, bool(als), vals["x_needs_review"],
        )
        return building_id

    except Exception as e:
        logger.warning("_get_or_create_building failed for '%s': %s", building_name, e)
        return None


# ---------------------------------------------------------------------------
# Multi-unit sync (listing_list)
# ---------------------------------------------------------------------------

def _sync_units(models: Any, uid: int, api_key: str, state: DocumentState, doc_url: str | None, building_id: int | None = None) -> list[int]:
    """Create/update one x_c21_listing record per unit in a listing_list document."""
    raw: dict = state.extracted.raw if state.extracted else {}
    units = raw.get("units") or []
    ids: list[int] = []
    top_building = raw.get("building_name")  # FORMAT A: building shared across all units
    top_address = raw.get("address")

    for unit in units[:20]:
        if not isinstance(unit, dict):
            continue
        vals = _map_unit_fields(raw, unit, doc_url, state.file_name)
        if not vals:
            continue

        # For FORMAT B flyers (multi-building), each unit has its own building → resolve separately
        unit_building_name = unit.get("building_name") or ""
        if unit_building_name and unit_building_name != top_building:
            unit_building_id = _get_or_create_building(models, uid, api_key, {**raw, "building_name": unit_building_name})
        else:
            unit_building_id = building_id
        if unit_building_id:
            vals["x_building_id"] = unit_building_id

        # Precise dedup: building + floor/unit as separate fields beats ilike on full x_name
        unit_building = unit.get("building_name") or top_building
        unit_address = unit.get("address") or top_address
        floor_unit = " ".join(str(x) for x in (unit.get("floor"), unit.get("unit")) if x)
        existing_id = _find_unit_record(models, uid, api_key, unit_building, unit_address, floor_unit)

        try:
            ids.append(_create_or_update(models, uid, api_key, existing_id or "", vals))
        except Exception as e:
            logger.warning("Odoo sync: unit record failed for '%s': %s", vals.get("x_name"), e)
    return ids


def _find_unit_record(
    models: Any, uid: int, api_key: str,
    building: str | None, address: str | None, floor_unit: str,
) -> str | None:
    """Find an existing Odoo unit record by building name + floor/unit, or address + floor/unit.

    Returns the record ID as a string, or None if not found.
    Searching building + floor_unit separately is more reliable than ilike on the
    concatenated x_name because floor notation varies ("3/F" vs "3樓").
    """
    if not floor_unit:
        return None

    # Try: building name contains + exact floor_unit match
    if building:
        found = models.execute_kw(
            ODOO_DB, uid, api_key, ODOO_MODEL, "search",
            [[["x_name", "ilike", building], ["x_c21_floor_unit", "=", floor_unit]]],
        )
        if found:
            return str(found[0])

    # Fallback: address + floor_unit
    if address:
        found = models.execute_kw(
            ODOO_DB, uid, api_key, ODOO_MODEL, "search",
            [[["x_c21_address", "ilike", address], ["x_c21_floor_unit", "=", floor_unit]]],
        )
        if found:
            return str(found[0])

    return None


def _map_unit_fields(raw: dict, unit: dict, doc_url: str | None, file_name: str = "") -> dict | None:
    """Map one unit entry → Odoo vals. Unit-level fields win over document-level."""
    building = unit.get("building_name") or raw.get("building_name")
    address = unit.get("address") or raw.get("address")

    floor_unit = " ".join(str(x) for x in (unit.get("floor"), unit.get("unit")) if x)

    name_base = building or address
    if not name_base:
        return None
    name = f"{name_base} {floor_unit}".strip() if floor_unit else str(name_base)

    vals: dict = {"x_name": name, "x_c21_status": "active"}
    if address:
        vals["x_c21_address"] = address

    district_text = unit.get("district") or raw.get("district") or ""
    # Fall back to Odoo's "other" bucket for districts not in the selection (e.g. 佐敦, 土瓜灣)
    district_key = _map_district(district_text) or ("other" if district_text.strip() else None)
    if district_key:
        vals["x_c21_district"] = district_key

    if floor_unit:
        vals["x_c21_floor_unit"] = floor_unit

    type_key = _map_property_type(unit.get("property_type") or raw.get("property_type") or "")
    if type_key:
        vals["x_c21_property_type"] = type_key

    # Date received: from filename if present, else today (processing date)
    vals["x_c21_date_received"] = _extract_date(file_name) or date.today().isoformat()

    for src_key, odoo_field in (("size", "x_c21_size_sqft"), ("rent", "x_c21_rent_net")):
        v = unit.get(src_key)
        if v is not None:
            try:
                vals[odoo_field] = float(v)
            except (TypeError, ValueError):
                pass

    if raw.get("contact_name"):
        vals["x_c21_contact_name"] = raw["contact_name"]
    if raw.get("contact_phone"):
        vals["x_c21_contact_phone"] = raw["contact_phone"]

    notes = []
    if unit.get("features"):
        notes.append(f"<p>{unit['features']}</p>")
    if doc_url:
        notes.append(f'<p>業主放盤文件：<a href="{doc_url}" target="_blank">開啟文件 Open Document</a></p>')
    if notes:
        vals["x_c21_notes"] = "".join(notes)

    return vals


# ---------------------------------------------------------------------------
# Field mapping
# ---------------------------------------------------------------------------

_PROPERTY_TYPE_ZH = {
    "retail": "商舖", "office": "寫字樓", "residential": "住宅", "industrial": "工廈",
}


def _build_listing_name(raw: dict, file_name: str) -> str:
    """Build a descriptive x_name even from teaser ads with no address.

    Teaser ads (IG/WhatsApp promos) often carry only a district, a listing ref
    (樓盤編號) and a headline — a bare district like "中環" makes a useless record
    name, so enrich short names with type and ref: "中環 商舖 #10978".
    """
    base = (raw.get("building_name") or raw.get("project_name")
            or raw.get("address") or "").strip()
    ref = str(raw.get("listing_ref") or "").strip().lstrip("#")
    headline = str(raw.get("headline") or "").strip()

    # A bare district or very short base is not identifying — enrich it
    if len(base) <= 4:
        district = str(raw.get("district") or "").strip()
        ptype = _PROPERTY_TYPE_ZH.get(str(raw.get("property_type") or "").lower(), "")
        parts = [p for p in (base or district, ptype) if p]
        candidate = " ".join(parts) if parts else (headline or "")
        if ref:
            candidate = f"{candidate} #{ref}".strip()
        if candidate:
            return candidate
    elif ref and ref not in base:
        return f"{base} #{ref}"

    return base or headline or file_name


def _map_fields(state: DocumentState, doc_url: str | None, building_id: int | None = None) -> dict:
    """Map AI extracted_data → Odoo x_c21_listing field values.

    Only non-null values are included so existing manual edits in Odoo are preserved.
    """
    raw: dict = state.extracted.raw if state.extracted else {}

    name = _build_listing_name(raw, state.file_name)
    vals: dict = {"x_name": name, "x_c21_status": "active"}
    if building_id:
        vals["x_building_id"] = building_id

    if raw.get("address"):
        vals["x_c21_address"] = raw["address"]

    district_key = _map_district(raw.get("district") or raw.get("area") or "")
    if district_key:
        vals["x_c21_district"] = district_key

    type_key = _map_property_type(raw.get("property_type") or "")
    if type_key:
        vals["x_c21_property_type"] = type_key

    size = raw.get("size_sqft") or raw.get("total_gfa_sqft") or raw.get("typical_floor_sqft")
    if size is not None:
        try:
            vals["x_c21_size_sqft"] = float(size)
        except (TypeError, ValueError):
            pass

    # First available unit: floor/unit label + rent + size fallback
    units = raw.get("available_units") or []
    if units and isinstance(units, list):
        unit = units[0]
        if isinstance(unit, dict):
            floor_unit = unit.get("floor") or unit.get("unit")
            if floor_unit:
                vals["x_c21_floor_unit"] = str(floor_unit)
            rent = unit.get("rent_monthly")
            if rent is not None:
                try:
                    vals["x_c21_rent_net"] = float(rent)
                except (TypeError, ValueError):
                    pass
            # Size fallback: if not captured at top level, use first unit's size
            if "x_c21_size_sqft" not in vals and unit.get("size_sqft") is not None:
                try:
                    vals["x_c21_size_sqft"] = float(unit["size_sqft"])
                except (TypeError, ValueError):
                    pass

    # Top-level rent fallback (asking_rent for pitching decks, rent_monthly for listings)
    if "x_c21_rent_net" not in vals:
        for rent_key in ("asking_rent", "rent_monthly"):
            if raw.get(rent_key) is not None:
                try:
                    vals["x_c21_rent_net"] = float(raw[rent_key])
                    break
                except (TypeError, ValueError):
                    pass

    if raw.get("contact_name"):
        vals["x_c21_contact_name"] = raw["contact_name"]
    if raw.get("contact_phone"):
        vals["x_c21_contact_phone"] = raw["contact_phone"]

    # Specs — present in ground-floor shop listings
    for ai_key, odoo_field in [
        ("electrical", "x_c21_electrical"),
        ("drainage", "x_c21_drainage"),
        ("aircon", "x_c21_aircon"),
        ("water_supply", "x_c21_water"),
        ("handover", "x_c21_handover"),
    ]:
        if raw.get(ai_key):
            vals[odoo_field] = str(raw[ai_key])

    if raw.get("gas_supply") is not None:
        vals["x_c21_gas"] = bool(raw["gas_supply"])

    if raw.get("management_fee_psf") is not None:
        try:
            vals["x_c21_mgmt_fee_psf"] = float(raw["management_fee_psf"])
        except (TypeError, ValueError):
            pass

    date_received = _extract_date(state.file_name)
    if date_received:
        vals["x_c21_date_received"] = date_received

    if doc_url:
        vals["x_c21_notes"] = (
            f'<p>業主放盤文件：<a href="{doc_url}" target="_blank">開啟文件 Open Document</a></p>'
        )

    return vals


# ---------------------------------------------------------------------------
# Create or update Odoo record
# ---------------------------------------------------------------------------

def _create_or_update(models: Any, uid: int, api_key: str, existing_id: str, vals: dict) -> int:
    """Update existing Odoo record or create a new one. Returns the record ID."""
    # 1. Known record ID from previous run — try update first
    if existing_id:
        try:
            found = models.execute_kw(
                ODOO_DB, uid, api_key, ODOO_MODEL, "search",
                [[["id", "=", int(existing_id)]]],
            )
            if found:
                models.execute_kw(ODOO_DB, uid, api_key, ODOO_MODEL, "write",
                                  [[int(existing_id)], vals])
                return int(existing_id)
        except Exception:
            pass  # Record deleted in Odoo — fall through to search/create

    # 2. Search by listing name (ilike = partial match, handles truncated AI extractions)
    name = vals.get("x_name", "")
    if name:
        found = models.execute_kw(
            ODOO_DB, uid, api_key, ODOO_MODEL, "search",
            [[["x_name", "ilike", name]]],
        )
        if not found:
            # Fallback: search by address
            address = vals.get("x_c21_address", "")
            if address:
                found = models.execute_kw(
                    ODOO_DB, uid, api_key, ODOO_MODEL, "search",
                    [[["x_c21_address", "ilike", address]]],
                )
        if found:
            record_id = found[0]
            models.execute_kw(ODOO_DB, uid, api_key, ODOO_MODEL, "write",
                              [[record_id], vals])
            return record_id

    # 3. Create new record
    return models.execute_kw(ODOO_DB, uid, api_key, ODOO_MODEL, "create", [vals])


# ---------------------------------------------------------------------------
# Azure AI Search patch
# ---------------------------------------------------------------------------

def _patch_search_doc(doc_id: str, odoo_record_id: str, sync_status: str, source_url: str | None) -> None:
    """Merge-update the Azure Search document with Odoo sync result fields."""
    if not doc_id:
        return
    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    api_key = os.environ.get("AZURE_SEARCH_API_KEY")
    index_name = os.environ.get("AZURE_SEARCH_INDEX", "processed-documents")
    if not endpoint or not api_key:
        return
    url = f"{endpoint}/indexes/{index_name}/docs/index?api-version=2024-07-01"
    merge: dict = {
        "@search.action": "merge",
        "id": doc_id,
        "odoo_record_id": odoo_record_id,
        "odoo_sync_status": sync_status,
    }
    if source_url:
        merge["source_url"] = source_url
    body = {"value": [merge]}
    try:
        with httpx.Client(timeout=30) as client:
            client.post(
                url,
                headers={"api-key": api_key, "Content-Type": "application/json"},
                json=body,
            )
    except Exception as e:
        logger.warning("Odoo sync: failed to patch Azure Search doc %s: %s", doc_id, e)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _map_district(raw: str) -> str | None:
    if not raw:
        return None
    return DISTRICT_MAP.get(raw.strip()) or DISTRICT_MAP.get(raw.strip().lower())


def _map_property_type(raw: str) -> str | None:
    if not raw:
        return None
    return PROPERTY_TYPE_MAP.get(raw.strip()) or PROPERTY_TYPE_MAP.get(raw.strip().lower())


def _extract_date(file_name: str) -> str | None:
    """Extract YYYY-MM-DD from filenames containing 8-digit dates (e.g. 20260505)."""
    m = re.search(r"(\d{4})(\d{2})(\d{2})", file_name)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            pass
    return None
