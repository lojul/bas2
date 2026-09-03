"""Odoo sync node — creates or updates C21 放盤管理 records after extraction.

Fully non-blocking: any Odoo failure is logged and the pipeline continues.

Logic:
  1. Skip non-property doc types (news, contact)
  2. Upload PDF to Odoo Documents (folder "Property Listings", ID 58)
  3. listing → one record; listing_list → ONE RECORD PER UNIT;
     pitching_deck → one record, or ONE RECORD PER UNIT if available_units has >1 entry
  4. If state.odoo_record_id is set → update that record (reprocessing path)
     Otherwise → search by x_name, then x_c21_address → update if found, else create
  5. Write unmapped AI fields to x_c21_extra_field (key-value overflow table)

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

EXTRA_FIELD_MODEL = "x_c21_extra_field"

# Fields that staff routinely hand-edit in Odoo after a listing is created
# (renaming to a clean display name, marking a unit withdrawn/leased). A rerun
# of the same source PDF must not clobber these on an UPDATE — only set them
# when creating a brand-new record. See _strip_manual_fields.
_MANUAL_OVERRIDE_FIELDS: frozenset[str] = frozenset({"x_name", "x_c21_status"})


def _strip_manual_fields(vals: dict) -> dict:
    """Return a copy of vals with staff-editable fields removed, for use on UPDATE only.

    Without this, every rerun of the same PDF (e.g. a Slack re-test) silently
    reverts a manually-cleaned x_name back to the verbose AI-generated form, and
    resets x_c21_status back to 'active' even if staff had marked the unit
    withdrawn/leased — undoing the archive-on-withdraw workflow. Confirmed via a
    live rerun in Odoo, 2026-09-03.
    """
    return {k: v for k, v in vals.items() if k not in _MANUAL_OVERRIDE_FIELDS}

# AI extraction keys that map to explicit Odoo columns on x_c21_listing.
# Anything in raw NOT in this set goes to x_c21_extra_field.
_KNOWN_AI_KEYS: frozenset[str] = frozenset({
    "building_name", "project_name", "address", "district", "area",
    "property_type", "size_sqft", "total_gfa_sqft", "typical_floor_sqft",
    "available_units", "asking_rent", "rent_monthly",
    "contact_name", "contact_phone",
    "electrical", "drainage", "aircon", "water_supply", "handover",
    "gas_supply", "management_fee_psf", "ceiling_height",
    "rates_quarterly", "govt_rent_quarterly",
    "listing_ref", "headline",
    # nested / meta keys — not written as extra fields
    "units", "_extraction_failed", "_no_data",
})

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

        # Grab PDF bytes once, before Documents upload — reused for photo extraction
        # below. Not cleared from state until every return path (photo extraction
        # needs them too, so the old "clear right after Documents upload" spot was
        # too early).
        pdf_bytes = _get_pdf_bytes(state)
        doc_url = _upload_to_documents(models, uid, api_key, state, pdf_bytes)

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
                state.file_bytes = None
                return state
            _sync_photos(models, uid, api_key, state, pdf_bytes, ids)
            state.odoo_record_id = ",".join(map(str, ids))
            state.odoo_sync_status = "synced"
            logger.info(
                "Odoo sync complete for '%s': %d unit records %s",
                state.file_name, len(ids), ids,
            )
            state.file_bytes = None
            return state

        pitching_units = raw.get("available_units") or []
        if state.document_type == DocumentType.PITCHING_DECK and len(pitching_units) > 1:
            # Pitching deck describing MULTIPLE units (e.g. one flyer, several floors) —
            # one Odoo record per unit, same as listing_list, but using the
            # available_units[] schema (size_sqft/rent_monthly keys, not size/rent).
            ids = _sync_pitching_deck_units(models, uid, api_key, state, doc_url, building_id, pitching_units)
            if not ids:
                state.odoo_sync_status = "skipped"
                logger.info("Odoo sync: no units extracted for '%s', skipping", state.file_name)
                state.file_bytes = None
                return state
            _sync_photos(models, uid, api_key, state, pdf_bytes, ids)
            state.odoo_record_id = ",".join(map(str, ids))
            state.odoo_sync_status = "synced"
            logger.info(
                "Odoo sync complete for '%s': %d unit records %s",
                state.file_name, len(ids), ids,
            )
            state.file_bytes = None
            return state

        vals = _map_fields(state, doc_url, building_id)
        odoo_id = _create_or_update(models, uid, api_key, state.odoo_record_id, vals)

        # Write unmapped AI fields to x_c21_extra_field
        unmapped = _extract_unmapped(raw)
        _sync_extra_fields(models, uid, api_key, odoo_id, unmapped)
        _sync_photos(models, uid, api_key, state, pdf_bytes, [odoo_id])

        state.odoo_record_id = str(odoo_id)
        state.odoo_sync_status = "synced"

        logger.info(
            "Odoo sync complete for '%s': record ID %s, extra_fields=%d, doc_url=%s",
            state.file_name, odoo_id, len(unmapped), doc_url or "none",
        )

    except Exception as e:
        logger.error("Odoo sync error for '%s': %s", state.file_name, e)
        state.odoo_sync_status = "error"
        state.odoo_error_detail = str(e)

    state.file_bytes = None
    return state


# ---------------------------------------------------------------------------
# Odoo Documents upload
# ---------------------------------------------------------------------------

def _get_pdf_bytes(state: DocumentState) -> bytes | None:
    """Return the source PDF's raw bytes, downloading from blob storage if needed.

    Shared by _upload_to_documents and _sync_photos so the PDF is only fetched once.
    """
    if state.file_bytes:
        return state.file_bytes
    if state.blob_url:
        try:
            with httpx.Client(timeout=60) as client:
                resp = client.get(state.blob_url)
                resp.raise_for_status()
                return resp.content
        except Exception as e:
            logger.warning("Odoo sync: PDF download failed for '%s': %s", state.file_name, e)
    return None


def _upload_to_documents(models: Any, uid: int, api_key: str, state: DocumentState, pdf_bytes: bytes | None) -> str | None:
    """Upload PDF to Odoo Documents folder 58 and return the shareable URL."""
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
            "access_via_link": "view",
        }])

    doc_data = models.execute_kw(
        ODOO_DB, uid, api_key, "documents.document", "read",
        [[doc_id], ["access_token"]],
    )
    token = doc_data[0].get("access_token") if doc_data else None
    return f"{ODOO_URL}/odoo/documents/{token}" if token else None


# ---------------------------------------------------------------------------
# Photo sync — embedded PDF images → Odoo product photos
# ---------------------------------------------------------------------------

_PAGE_BREAK_RE = re.compile(r"<!--\s*PageBreak\s*-->")
_MD_HEADING_RE = re.compile(r"^##\s+(.+)$", re.M)
_NON_ALNUM_RE = re.compile(r"[^\w/]+")

MAX_SYNCED_IMAGES = 30
MIN_IMAGE_DIM = 100  # px — filters out logos/icons/alpha-mask fragments


def _extract_pdf_images(pdf_bytes: bytes, max_images: int = MAX_SYNCED_IMAGES) -> list[tuple[int, bytes, str, int, int]]:
    """Extract embedded photos/floor plans from a PDF via PyMuPDF, keeping page numbers.

    Returns (page_num [1-indexed], image_bytes, ext, width, height) tuples, in
    page order. Skips tiny images (<100px either side) — these are logos, icons,
    and colour-swatch fragments, never real content; verified against `pdfimages
    -list` on a real leasing deck (2026-09-03): this filter matched pdfimages'
    "real photo" count exactly, with zero false positives/negatives.
    """
    import fitz  # PyMuPDF — already a dependency (used by ocr.py)

    out: list[tuple[int, bytes, str, int, int]] = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for page_index in range(len(doc)):
            if len(out) >= max_images:
                break
            page = doc[page_index]
            seen_xrefs: set[int] = set()
            for img_info in page.get_images(full=True):
                if len(out) >= max_images:
                    break
                xref = img_info[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                try:
                    base = doc.extract_image(xref)
                except Exception:
                    continue
                if not base:
                    continue
                w, h = base.get("width", 0), base.get("height", 0)
                if w < MIN_IMAGE_DIM or h < MIN_IMAGE_DIM:
                    continue
                out.append((page_index + 1, base["image"], base.get("ext", "jpg"), w, h))
    finally:
        doc.close()
    return out


def _split_ocr_pages(ocr_text: str) -> list[str]:
    """Split Azure Document Intelligence markdown into per-page chunks."""
    return _PAGE_BREAK_RE.split(ocr_text)


def _page_heading(page_text: str) -> str | None:
    """First '## heading' on a page, if any (used to detect a floor/unit label)."""
    m = _MD_HEADING_RE.search(page_text)
    return m.group(1).strip() if m else None


def _match_floor_unit(heading: str, unit_floor: dict[int, str]) -> int | None:
    """Loosely match a page heading (e.g. '1/F 樓') against each unit's x_c21_floor_unit."""
    h = _NON_ALNUM_RE.sub("", heading).lower()
    if not h:
        return None
    for listing_id, floor in unit_floor.items():
        f = _NON_ALNUM_RE.sub("", floor or "").lower()
        if f and (f in h or h in f):
            return listing_id
    return None


def _sync_photos(
    models: Any, uid: int, api_key: str, state: DocumentState,
    pdf_bytes: bytes | None, unit_ids: list[int],
) -> None:
    """Extract embedded photos/floor plans from the source PDF and attach them to
    each synced unit's linked product (gallery images + main thumbnail).

    Best-effort and fully non-blocking — any failure here is logged and swallowed,
    never fails the listing sync that already succeeded.

    Page 1 is always treated as the building/cover photo and set as every synced
    unit's product.image_1920 (main thumbnail). For a single-unit document, every
    other extracted image goes straight into that unit's photo gallery. For a
    multi-unit document, remaining pages are assigned to a unit by matching a
    '## <floor label>' markdown heading (from the OCR text) against that unit's
    x_c21_floor_unit, carrying the last-matched heading forward across pages that
    don't have their own — this matches the common HK leasing-brochure layout of
    one floor-plan-then-photos section per unit (verified against a real 2-unit
    deck, 2026-09-03). Any page that can't be matched to a specific unit is
    attached to every unit rather than silently dropped.
    """
    if not pdf_bytes or not unit_ids:
        return
    try:
        images = _extract_pdf_images(pdf_bytes)
    except Exception as e:
        logger.warning("Odoo sync: photo extraction failed for '%s': %s", state.file_name, e)
        return
    if not images:
        return

    try:
        listings = models.execute_kw(
            ODOO_DB, uid, api_key, ODOO_MODEL, "read",
            [unit_ids], {"fields": ["id", "x_c21_floor_unit", "x_c21_product_id"]},
        )
    except Exception as e:
        logger.warning("Odoo sync: could not read units for photo sync on '%s': %s", state.file_name, e)
        return

    unit_floor: dict[int, str] = {r["id"]: (r.get("x_c21_floor_unit") or "") for r in listings}
    unit_product: dict[int, int] = {
        r["id"]: r["x_c21_product_id"][0] for r in listings if r.get("x_c21_product_id")
    }
    if not unit_product:
        return

    cover = images[0] if images[0][0] == 1 else None
    gallery_images = images[1:] if cover else images

    # Multi-unit: map each remaining page to a unit via OCR heading carry-forward.
    # Single-unit: every remaining image belongs to that one unit — no mapping needed.
    page_unit: dict[int, int] = {}
    if len(unit_ids) > 1 and state.ocr and state.ocr.text:
        pages = _split_ocr_pages(state.ocr.text)
        current_unit: int | None = None
        for page_num in range(1, len(pages) + 1):
            heading = _page_heading(pages[page_num - 1])
            if heading:
                matched = _match_floor_unit(heading, unit_floor)
                if matched is not None:
                    current_unit = matched
            if current_unit is not None:
                page_unit[page_num] = current_unit

    for unit_id in unit_ids:
        product_id = unit_product.get(unit_id)
        if not product_id:
            continue

        if cover:
            _, img_bytes, _ext, _w, _h = cover
            try:
                models.execute_kw(ODOO_DB, uid, api_key, "product.template", "write",
                                  [[product_id], {"image_1920": base64.b64encode(img_bytes).decode()}])
            except Exception as e:
                logger.warning("Odoo sync: cover image write failed for product %s: %s", product_id, e)

        if len(unit_ids) == 1:
            my_images = gallery_images
        else:
            # No confident mapping for this page → attach to every unit (never drop it)
            my_images = [img for img in gallery_images if page_unit.get(img[0], unit_id) == unit_id]

        # Reprocessing the same PDF (e.g. a Slack re-test) must not pile up a second
        # copy of every gallery photo — delete this product's previously auto-synced
        # set (identified by our own "p<page> 圖片 <n>" naming) before recreating it.
        # Staff-curated images use a different naming convention and are left alone.
        # Confirmed via a live rerun in Odoo, 2026-09-03: without this, image count
        # doubled on every reprocess.
        try:
            stale = models.execute_kw(
                ODOO_DB, uid, api_key, "product.image", "search",
                [[["product_tmpl_id", "=", product_id], ["name", "=like", "p%圖片%"]]],
            )
            if stale:
                models.execute_kw(ODOO_DB, uid, api_key, "product.image", "unlink", [stale])
        except Exception as e:
            logger.warning("Odoo sync: stale gallery image cleanup failed for product %s: %s", product_id, e)

        for idx, (page_num, img_bytes, _ext, _w, _h) in enumerate(my_images, start=1):
            name = f"p{page_num} 圖片 {idx}"
            try:
                models.execute_kw(ODOO_DB, uid, api_key, "product.image", "create", [{
                    "name": name,
                    "image_1920": base64.b64encode(img_bytes).decode(),
                    "product_tmpl_id": product_id,
                }])
            except Exception as e:
                logger.warning("Odoo sync: gallery image write failed for product %s: %s", product_id, e)


# ---------------------------------------------------------------------------
# Building parent — find or create
# ---------------------------------------------------------------------------

def _address_overlap(ai_address: str, als_address: str, minlen: int = 2) -> bool:
    """True if any Chinese substring (>=minlen chars) of ai_address appears in als_address.

    ALS's fuzzy building-name search sometimes returns a plausible-but-wrong building
    at the same confidence score as a correct match (e.g. "Enterprise Square 3" →
    a different "常悅道 9號"; "United Building" → a different "順聯大廈" in Central
    instead of the correct one in Fortress Hill). Confidence alone can't distinguish
    these. Cross-checking the street name against the AI's own extracted address can:
    the correct match always shares a street-name substring, the wrong one never does
    (verified against both real-world cases above).
    """
    if not ai_address or not als_address:
        return True  # nothing to cross-check against — don't block on missing data
    tokens = re.findall(r"[一-鿿]+", ai_address)
    for token in tokens:
        for length in range(len(token), minlen - 1, -1):
            for i in range(len(token) - length + 1):
                sub = token[i:i + length]
                if len(sub) >= minlen and sub in als_address:
                    return True
    return False


def _get_or_create_building(models: Any, uid: int, api_key: str, raw: dict) -> int | None:
    """Return Odoo x_c21_building record ID, creating it if needed.

    Resolution order:
    1. ALS lookup on building name → canonical name + GeoAddress dedup key
    2. Cross-check ALS's address against the AI-extracted address — reject the ALS
       match entirely if they share no street-name overlap (see _address_overlap)
    3. Search Odoo by ALS GeoAddress (exact, permanent key) — only if step 2 passed
    4. Search Odoo by building name (ilike, fallback when ALS misses or was rejected)
    5. Create new building record (with needs_review=True if ALS missed/was rejected)
    """
    building_name = (raw.get("building_name") or raw.get("project_name") or "").strip()
    if not building_name:
        return None

    try:
        # ALS lookup for canonical data + dedup key
        als = lookup_building(building_name)

        if als and not _address_overlap(raw.get("address") or "", als.address_zh or ""):
            logger.warning(
                "ALS match for '%s' rejected — no address overlap (ALS: %s, AI: %s)",
                building_name, als.address_zh, raw.get("address"),
            )
            als = None

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

        # Fallback: search by x_name_en too — x_name alone misses a building whose
        # Chinese name was manually shortened in Odoo (e.g. "Connaught Marina 干諾中心"
        # → "干諾中心" with "Connaught Marina" moved to x_name_en), since ilike only
        # matches when the FIELD contains the search string, not the reverse.
        found = models.execute_kw(
            ODOO_DB, uid, api_key, BUILDING_MODEL, "search",
            [[["x_name_en", "ilike", search_name]]],
        )
        if found:
            return found[0]

        # Last-resort fallback: address overlap. Catches renames that also don't share
        # a common substring at all (e.g. name shortened AND reordered) — the street
        # address is a much more stable identifier than a free-text building name.
        ai_address = raw.get("address") or ""
        if ai_address:
            candidates = models.execute_kw(
                ODOO_DB, uid, api_key, BUILDING_MODEL, "search_read",
                [[["x_address", "!=", False]]], {"fields": ["id", "x_address"]},
            )
            for cand in candidates:
                if _address_overlap(ai_address, cand.get("x_address") or ""):
                    return cand["id"]

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

def _extract_unmapped(raw: dict) -> dict:
    """Return AI-extracted fields that have no fixed Odoo column on x_c21_listing."""
    return {
        k: v for k, v in raw.items()
        if k not in _KNOWN_AI_KEYS and v is not None and v != "" and not isinstance(v, (list, dict))
    }


def _sync_extra_fields(models: Any, uid: int, api_key: str, listing_id: int, unmapped: dict) -> None:
    """Write unmapped AI fields to x_c21_extra_field as key-value rows.

    Full replace on each sync: deletes existing rows for this listing, then re-creates.
    """
    if not unmapped:
        return
    try:
        existing = models.execute_kw(
            ODOO_DB, uid, api_key, EXTRA_FIELD_MODEL, "search",
            [[["x_listing_id", "=", listing_id]]],
        )
        if existing:
            models.execute_kw(ODOO_DB, uid, api_key, EXTRA_FIELD_MODEL, "unlink", [existing])

        rows = [
            {"x_listing_id": listing_id, "x_field_name": k, "x_field_value": str(v)}
            for k, v in unmapped.items()
        ]
        if rows:
            models.execute_kw(ODOO_DB, uid, api_key, EXTRA_FIELD_MODEL, "create", [rows])
            logger.info("extra_fields: wrote %d rows for listing %s", len(rows), listing_id)
    except Exception as e:
        logger.warning("_sync_extra_fields failed for listing %s: %s", listing_id, e)


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
        ocr_text = state.ocr.text if state.ocr and state.ocr.text else None
        vals = _map_unit_fields(raw, unit, doc_url, state.file_name, ocr_text)
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

        # Flag for re-sync to BAS — new records already default to False via ir.default,
        # but write() doesn't apply defaults, so set it explicitly for reprocessed records.
        vals["x_c21_published"] = False

        try:
            if existing_id:
                # Update the known record directly — no fuzzy fallback. Preserve any
                # manual x_name/x_c21_status edit — see _strip_manual_fields.
                models.execute_kw(ODOO_DB, uid, api_key, ODOO_MODEL, "write",
                                  [[int(existing_id)], _strip_manual_fields(vals)])
                unit_id = int(existing_id)
            else:
                # No prior record found — always create a new one.
                # Do NOT use _create_or_update here: its ilike fallback matches any record
                # with the same building name, collapsing multiple floors into one record.
                unit_id = models.execute_kw(ODOO_DB, uid, api_key, ODOO_MODEL, "create", [vals])
            if unit_id not in ids:
                ids.append(unit_id)
            # Extra fields per unit (unit-level fields that didn't fit known columns)
            unit_unmapped = _extract_unmapped({k: v for k, v in unit.items() if k not in {
                "building_name", "address", "floor", "unit", "district",
                "property_type", "size", "rent", "price", "features",
            }})
            _sync_extra_fields(models, uid, api_key, unit_id, unit_unmapped)
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


def _map_unit_fields(
    raw: dict, unit: dict, doc_url: str | None, file_name: str = "", ocr_text: str | None = None,
) -> dict | None:
    """Map one unit entry → Odoo vals. Unit-level fields win over document-level."""
    building = unit.get("building_name") or raw.get("building_name")
    address = unit.get("address") or raw.get("address")

    floor_unit = " ".join(str(x) for x in (unit.get("floor"), unit.get("unit")) if x)

    name_base = building or address
    if not name_base:
        return None
    name = f"{name_base} {floor_unit}".strip() if floor_unit else str(name_base)

    vals: dict = {"x_name": name, "x_c21_status": "active"}
    if ocr_text:
        vals["x_c21_ocr_text"] = ocr_text
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
        vals["x_c21_doc_url"] = doc_url
        notes.append(f'<p>業主放盤文件：<a href="{doc_url}" target="_blank">開啟文件 Open Document</a></p>')
    if notes:
        vals["x_c21_notes"] = "".join(notes)

    return vals


def _sync_pitching_deck_units(
    models: Any, uid: int, api_key: str, state: DocumentState,
    doc_url: str | None, building_id: int | None, units: list,
) -> list[int]:
    """Create/update one x_c21_listing record per unit in a multi-unit pitching_deck.

    Unlike listing_list (_sync_units), a pitching deck describes ONE building with
    several floors/units using the available_units[] schema (size_sqft/rent_monthly,
    not size/rent) — so this reuses _map_fields(unit=...) rather than _map_unit_fields.
    """
    raw: dict = state.extracted.raw if state.extracted else {}
    building = raw.get("building_name") or raw.get("project_name")
    address = raw.get("address")
    ids: list[int] = []

    for unit in units[:20]:
        if not isinstance(unit, dict):
            continue
        vals = _map_fields(state, doc_url, building_id, unit=unit)

        # Dedup key MUST match what _map_fields actually stores in x_c21_floor_unit
        # (floor, falling back to unit — not both joined) or an existing record with
        # only one of the two populated will never be found, creating a duplicate.
        floor_unit = str(unit.get("floor") or unit.get("unit") or "")
        existing_id = _find_unit_record(models, uid, api_key, building, address, floor_unit)
        vals["x_c21_published"] = False

        try:
            if existing_id:
                # Preserve any manual x_name/x_c21_status edit — see _strip_manual_fields.
                models.execute_kw(ODOO_DB, uid, api_key, ODOO_MODEL, "write",
                                  [[int(existing_id)], _strip_manual_fields(vals)])
                unit_id = int(existing_id)
            else:
                unit_id = models.execute_kw(ODOO_DB, uid, api_key, ODOO_MODEL, "create", [vals])
            if unit_id not in ids:
                ids.append(unit_id)
        except Exception as e:
            logger.warning("Odoo sync: pitching_deck unit record failed for '%s': %s", vals.get("x_name"), e)

    # Document-level unmapped AI fields go on every unit record (they're shared across units)
    unmapped = _extract_unmapped(raw)
    for unit_id in ids:
        _sync_extra_fields(models, uid, api_key, unit_id, unmapped)

    return ids


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


def _map_fields(
    state: DocumentState, doc_url: str | None, building_id: int | None = None,
    unit: dict | None = None,
) -> dict:
    """Map AI extracted_data → Odoo x_c21_listing field values.

    Only non-null values are included so existing manual edits in Odoo are preserved.

    `unit` overrides which entry of raw["available_units"] to use for floor/rent/size/
    rates (defaults to the first). Pass explicitly when syncing one record per unit
    (see _sync_pitching_deck_units) so each record gets its own unit's data instead
    of every unit collapsing onto available_units[0].
    """
    raw: dict = state.extracted.raw if state.extracted else {}

    name = _build_listing_name(raw, state.file_name)
    if unit and (unit.get("floor") or unit.get("unit")):
        floor_unit_suffix = " ".join(str(x) for x in (unit.get("floor"), unit.get("unit")) if x)
        name = f"{name} {floor_unit_suffix}".strip()
    vals: dict = {"x_name": name, "x_c21_status": "active"}
    if building_id:
        vals["x_building_id"] = building_id

    if state.ocr and state.ocr.text:
        vals["x_c21_ocr_text"] = state.ocr.text

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

    # Selected unit (defaults to the first): floor/unit label + rent + size + rates fallback
    units = raw.get("available_units") or []
    if unit is None and units and isinstance(units, list):
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
        # Size fallback: if not captured at top level, use this unit's size
        if "x_c21_size_sqft" not in vals and unit.get("size_sqft") is not None:
            try:
                vals["x_c21_size_sqft"] = float(unit["size_sqft"])
            except (TypeError, ValueError):
                pass
        if unit.get("rates_quarterly") is not None:
            try:
                vals["x_c21_rates"] = float(unit["rates_quarterly"])
            except (TypeError, ValueError):
                pass
        if unit.get("govt_rent_quarterly") is not None:
            try:
                vals["x_c21_govt_rent"] = float(unit["govt_rent_quarterly"])
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
        ("ceiling_height", "x_c21_ceiling_height"),
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

    # Total monthly management fee = psf × size — deterministic, no need to ask the LLM for it
    if "x_c21_mgmt_fee_psf" in vals and "x_c21_size_sqft" in vals:
        vals["x_c21_mgmt_fee"] = round(vals["x_c21_mgmt_fee_psf"] * vals["x_c21_size_sqft"], 2)

    date_received = _extract_date(state.file_name)
    if date_received:
        vals["x_c21_date_received"] = date_received

    if doc_url:
        vals["x_c21_doc_url"] = doc_url
        vals["x_c21_notes"] = (
            f'<p>業主放盤文件：<a href="{doc_url}" target="_blank">開啟文件 Open Document</a></p>'
        )

    return vals


# ---------------------------------------------------------------------------
# Create or update Odoo record
# ---------------------------------------------------------------------------

def _create_or_update(models: Any, uid: int, api_key: str, existing_id: str, vals: dict) -> int:
    """Update existing Odoo record or create a new one. Returns the record ID."""
    # Flag for re-sync to BAS — new records already default to False via ir.default,
    # but write() doesn't apply defaults, so set it explicitly here for all paths.
    vals["x_c21_published"] = False

    # 1. Known record ID from previous run — try update first
    if existing_id:
        try:
            found = models.execute_kw(
                ODOO_DB, uid, api_key, ODOO_MODEL, "search",
                [[["id", "=", int(existing_id)]]],
            )
            if found:
                # Preserve any manual x_name/x_c21_status edit — see _strip_manual_fields.
                models.execute_kw(ODOO_DB, uid, api_key, ODOO_MODEL, "write",
                                  [[int(existing_id)], _strip_manual_fields(vals)])
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
            # Preserve any manual x_name/x_c21_status edit — see _strip_manual_fields.
            models.execute_kw(ODOO_DB, uid, api_key, ODOO_MODEL, "write",
                              [[record_id], _strip_manual_fields(vals)])
            return record_id

    # 3. Create new record
    return models.execute_kw(ODOO_DB, uid, api_key, ODOO_MODEL, "create", [vals])


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
