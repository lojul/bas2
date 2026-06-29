"""Admin routes — document index management and runtime config."""

import json
import os
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from api.auth import get_current_user
from api.common import read_config, write_config

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
