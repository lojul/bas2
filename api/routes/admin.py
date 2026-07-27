"""Admin routes — document index management and runtime config."""

import json
import logging
import os
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel

from api.auth import get_current_user
from api.common import read_config, write_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


# ── Config ─────────────────────────────────────────────────────────────────────

class ConfigBody(BaseModel):
    inbox_folder: str | None = None
    processed_folder: str | None = None
    move_when_done: bool | None = None
    timer_enabled: bool | None = None
    ms_client_id: str | None = None
    ms_tenant_id: str | None = None
    ms_client_secret: str | None = None
    ms_drive_id: str | None = None


def _config_response(cfg: dict) -> dict:
    return {
        "inbox_folder": cfg.get("inbox_folder", ""),
        "processed_folder": cfg.get("processed_folder", "/Document Processor/Processed"),
        "move_when_done": cfg.get("move_when_done", False),
        "timer_enabled": cfg.get("timer_enabled", True),
        "ms_client_id": os.environ.get("MS_GRAPH_CLIENT_ID") or cfg.get("ms_client_id", ""),
        "ms_tenant_id": os.environ.get("MS_GRAPH_TENANT_ID") or cfg.get("ms_tenant_id", ""),
        "ms_client_secret_configured": bool(
            os.environ.get("MS_GRAPH_CLIENT_SECRET") or cfg.get("ms_client_secret", "")
        ),
        "ms_drive_id": os.environ.get("MS_GRAPH_DRIVE_ID") or cfg.get("ms_drive_id", ""),
    }


@router.get("/config")
def get_config(username: Annotated[str, Depends(get_current_user)] = None):
    """Read runtime configuration."""
    return _config_response(read_config())


@router.put("/config")
def update_config(
    body: ConfigBody,
    username: Annotated[str, Depends(get_current_user)] = None,
):
    """Update runtime configuration."""
    cfg = read_config()
    if body.inbox_folder is not None:
        cfg["inbox_folder"] = body.inbox_folder.strip()
    if body.processed_folder is not None:
        cfg["processed_folder"] = body.processed_folder.strip()
    if body.move_when_done is not None:
        cfg["move_when_done"] = body.move_when_done
    if body.timer_enabled is not None:
        cfg["timer_enabled"] = body.timer_enabled
    if body.ms_client_id is not None:
        cfg["ms_client_id"] = body.ms_client_id.strip()
    if body.ms_tenant_id is not None:
        cfg["ms_tenant_id"] = body.ms_tenant_id.strip()
    if body.ms_client_secret is not None and body.ms_client_secret.strip():
        cfg["ms_client_secret"] = body.ms_client_secret.strip()
    if body.ms_drive_id is not None:
        cfg["ms_drive_id"] = body.ms_drive_id.strip()
    try:
        write_config(cfg)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    return _config_response(cfg)


# ── Documents ──────────────────────────────────────────────────────────────────

@router.get("/documents")
def get_documents(
    top_k: int = Query(1000, ge=1, le=1000),
    needs_review: bool = Query(False),
    username: Annotated[str, Depends(get_current_user)] = None,
):
    """List indexed documents from Azure AI Search."""
    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    index = os.environ.get("AZURE_SEARCH_INDEX", "processed-documents")
    api_key = os.environ.get("AZURE_SEARCH_API_KEY")

    if not all([endpoint, api_key]):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Azure Search not configured")

    headers = {"api-key": api_key, "Content-Type": "application/json"}

    with httpx.Client(timeout=15) as client:
        count_url = f"{endpoint}/indexes/{index}/docs/$count?api-version=2024-07-01"
        count_resp = client.get(count_url, headers=headers)
        total_chunks = int(count_resp.text) if count_resp.status_code == 200 else 0

        search_url = f"{endpoint}/indexes/{index}/docs/search?api-version=2024-07-01"
        body: dict[str, Any] = {
            "search": "*",
            "top": top_k,
            "select": "id,file_name,document_type,processed_at,extracted_data,image_urls,needs_review,extraction_path",
            "orderby": "processed_at desc",
        }
        if needs_review:
            body["filter"] = "needs_review eq true"

        search_resp = client.post(search_url, headers=headers, json=body)
        if search_resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Azure Search error: {search_resp.status_code}",
            )
        docs = search_resp.json().get("value", [])

    files: dict[str, dict] = {}
    by_type: dict[str, int] = {}
    for doc in docs:
        fname = doc.get("file_name", "Unknown")
        dtype = doc.get("document_type", "unknown")
        extracted_raw = doc.get("extracted_data")
        if isinstance(extracted_raw, str):
            try:
                extracted_raw = json.loads(extracted_raw)
            except Exception:
                pass

        if fname not in files:
            files[fname] = {
                "id": doc.get("id"),
                "file_name": fname,
                "document_type": dtype,
                "processed_at": doc.get("processed_at"),
                "extracted_data": extracted_raw,
                "image_urls": doc.get("image_urls") or [],
                "needs_review": doc.get("needs_review", False),
                "extraction_path": doc.get("extraction_path", "structured"),
                "chunk_count": 1,
            }
            by_type[dtype] = by_type.get(dtype, 0) + 1
        else:
            files[fname]["chunk_count"] += 1
            existing_urls = set(files[fname].get("image_urls") or [])
            new_urls = doc.get("image_urls") or []
            if new_urls:
                files[fname]["image_urls"] = list(existing_urls | set(new_urls))

    return {
        "total_chunks": total_chunks,
        "total_files": len(files),
        "by_type": by_type,
        "files": list(files.values()),
    }


class UpdateDocumentBody(BaseModel):
    extracted_data: dict[str, Any]
    needs_review: bool | None = None


@router.patch("/documents/{doc_id}")
def update_document(
    doc_id: str,
    body: UpdateDocumentBody,
    username: Annotated[str, Depends(get_current_user)] = None,
):
    """Update extracted_data for a document in Azure AI Search."""
    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    index = os.environ.get("AZURE_SEARCH_INDEX", "processed-documents")
    api_key = os.environ.get("AZURE_SEARCH_API_KEY")

    if not all([endpoint, api_key]):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Azure Search not configured")

    url = f"{endpoint}/indexes/{index}/docs/index?api-version=2024-07-01"
    headers = {"api-key": api_key, "Content-Type": "application/json"}
    merge_doc: dict[str, Any] = {
        "@search.action": "merge",
        "id": doc_id,
        "extracted_data": json.dumps(body.extracted_data, ensure_ascii=False),
    }
    if body.needs_review is not None:
        merge_doc["needs_review"] = body.needs_review

    with httpx.Client(timeout=15) as client:
        resp = client.post(url, headers=headers, json={"value": [merge_doc]})
        if resp.status_code not in (200, 201):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Azure Search error {resp.status_code}: {resp.text[:200]}",
            )

    return {"ok": True}


# ── Odoo → Azure Search sync webhook ───────────────────────────────────────────

# Reverse maps for Odoo selection keys → human-readable strings stored in extracted_data
_DISTRICT_REVERSE: dict[str, str] = {
    "kwun_tong": "觀塘", "kwai_fong": "葵芳", "kwai_chung": "葵涌",
    "tsuen_wan": "荃灣", "mong_kok": "旺角", "tsim_sha_tsui": "尖沙咀",
    "causeway_bay": "銅鑼灣", "wan_chai": "灣仔", "central": "中環",
    "sheung_wan": "上環", "cheung_sha_wan": "長沙灣", "kowloon_bay": "九龍灣",
    "san_po_kong": "新蒲崗",
}
_PROPERTY_TYPE_REVERSE: dict[str, str] = {
    "ground_shop": "地舖", "office": "寫字樓", "industrial": "工廈",
    "retail": "商舖", "residential": "住宅",
}


def _sync_odoo_to_search(record_id: int, payload: dict) -> bool:
    """Find the Azure Search doc for this Odoo record and merge-update it.
    Returns True if a doc was found and patched."""
    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    api_key = os.environ.get("AZURE_SEARCH_API_KEY")
    index = os.environ.get("AZURE_SEARCH_INDEX", "processed-documents")
    if not endpoint or not api_key:
        logger.warning("Odoo webhook: Azure Search not configured")
        return False

    headers = {"api-key": api_key, "Content-Type": "application/json"}

    # Find the doc that matches this Odoo record ID
    search_url = f"{endpoint}/indexes/{index}/docs/search?api-version=2024-07-01"
    with httpx.Client(timeout=15) as client:
        resp = client.post(search_url, headers=headers, json={
            "filter": f"odoo_record_id eq '{record_id}'",
            "select": "id,extracted_data",
            "top": 1,
        })

    if resp.status_code != 200:
        logger.error("Odoo webhook: search failed %s", resp.text[:200])
        return False

    docs = resp.json().get("value", [])
    if not docs:
        logger.warning("Odoo webhook: no Search doc found for odoo_record_id=%s", record_id)
        return False

    doc = docs[0]
    doc_id = doc["id"]

    # Parse existing extracted_data and merge Odoo values on top
    try:
        existing = json.loads(doc.get("extracted_data") or "{}")
    except (json.JSONDecodeError, TypeError):
        existing = {}

    odoo_vals = {
        "address": payload.get("x_c21_address") or existing.get("address"),
        "district": _DISTRICT_REVERSE.get(payload.get("x_c21_district", ""), payload.get("x_c21_district")) or existing.get("district"),
        "property_type": _PROPERTY_TYPE_REVERSE.get(payload.get("x_c21_property_type", ""), payload.get("x_c21_property_type")) or existing.get("property_type"),
        "size_sqft": payload.get("x_c21_size_sqft") or existing.get("size_sqft"),
        "floor_unit": payload.get("x_c21_floor_unit") or existing.get("floor_unit"),
        "contact_name": payload.get("x_c21_contact_name") or existing.get("contact_name"),
        "contact_phone": payload.get("x_c21_contact_phone") or existing.get("contact_phone"),
        "management_fee_psf": payload.get("x_c21_mgmt_fee_psf") or existing.get("management_fee_psf"),
    }
    # Rent: write to both keys so downstream code finds it regardless of doc type
    rent = payload.get("x_c21_rent_net")
    if rent is not None:
        odoo_vals["asking_rent"] = rent
        odoo_vals["rent_monthly"] = rent

    # Merge: only overwrite with non-null Odoo values
    merged = {**existing, **{k: v for k, v in odoo_vals.items() if v is not None}}

    # Patch Azure Search
    patch_url = f"{endpoint}/indexes/{index}/docs/index?api-version=2024-07-01"
    with httpx.Client(timeout=15) as client:
        resp = client.post(patch_url, headers=headers, json={
            "value": [{
                "@search.action": "merge",
                "id": doc_id,
                "extracted_data": json.dumps(merged, ensure_ascii=False),
            }]
        })

    if resp.status_code in (200, 201):
        logger.info("Odoo webhook: patched Search doc %s for Odoo record %s", doc_id, record_id)
        return True

    logger.error("Odoo webhook: patch failed %s", resp.text[:200])
    return False


@router.post("/odoo/webhook")
def odoo_webhook(
    body: dict,
    key: str | None = Query(default=None),
    x_api_key: Annotated[str | None, Header()] = None,
):
    """Receive Odoo field-update webhooks and sync to Azure AI Search.

    Accepts key via ?key= query param (Odoo native webhook) or X-Api-Key header.
    Odoo sends: {"id": 16, "x_c21_address": "...", "x_c21_district": "central", ...}
    """
    expected_key = os.environ.get("ASSISTANT_API_KEY", "")
    provided_key = key or x_api_key
    if not expected_key or provided_key != expected_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    record_id = body.get("id")
    if not record_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing id")

    found = _sync_odoo_to_search(int(record_id), body)
    return {"ok": True, "synced": found, "record_id": record_id}
