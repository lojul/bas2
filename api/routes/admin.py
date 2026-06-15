"""Admin endpoints — LangSmith runs, Azure Search documents, OneDrive upload."""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from api.auth import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])

# ── Blob config helpers ────────────────────────────────────────────────────────

_CONFIG_BLOB = "config/settings.json"
_DEFAULT_CONFIG = {
    "inbox_folder": "/Document Processor/In",
    "move_when_done": False,
}


def _blob_url() -> str | None:
    account = os.environ.get("AZURE_BLOB_ACCOUNT")
    container = os.environ.get("AZURE_BLOB_CONTAINER", "property-pdf")
    sas = os.environ.get("AZURE_BLOB_WRITE_SAS", "")
    if not account:
        return None
    return f"https://{account}.blob.core.windows.net/{container}/{_CONFIG_BLOB}?{sas}"


def _read_config() -> dict:
    url = _blob_url()
    if not url:
        return _DEFAULT_CONFIG.copy()
    try:
        with httpx.Client(timeout=5) as client:
            r = client.get(url)
            if r.status_code == 200:
                data = r.json()
                return {**_DEFAULT_CONFIG, **data}
            if r.status_code == 404:
                return _DEFAULT_CONFIG.copy()
    except Exception:
        pass
    return _DEFAULT_CONFIG.copy()


def _write_config(cfg: dict) -> None:
    url = _blob_url()
    if not url:
        raise RuntimeError("Blob storage not configured")
    with httpx.Client(timeout=10) as client:
        r = client.put(
            url,
            content=json.dumps(cfg, ensure_ascii=False).encode(),
            headers={"x-ms-blob-type": "BlockBlob", "Content-Type": "application/json"},
        )
        r.raise_for_status()


# ── Config endpoints ───────────────────────────────────────────────────────────

class ConfigBody(BaseModel):
    inbox_folder: str | None = None
    move_when_done: bool | None = None


@router.get("/config")
def get_config(username: Annotated[str, Depends(get_current_user)] = None):
    """Read runtime configuration from blob storage."""
    return _read_config()


@router.put("/config")
def update_config(
    body: ConfigBody,
    username: Annotated[str, Depends(get_current_user)] = None,
):
    """Update runtime configuration in blob storage."""
    cfg = _read_config()
    if body.inbox_folder is not None:
        cfg["inbox_folder"] = body.inbox_folder.strip()
    if body.move_when_done is not None:
        cfg["move_when_done"] = body.move_when_done
    try:
        _write_config(cfg)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    return cfg


# ── LangSmith runs ─────────────────────────────────────────────────────────────

def _parse_run(run: dict) -> dict[str, Any]:
    inputs = run.get("inputs") or {}
    outputs = run.get("outputs") or {}
    file_name = inputs.get("file_name", "Unknown")
    doc_type = "unknown"
    run_status = "error" if run.get("error") else "success"
    extracted_data: dict[str, Any] = {}
    confidence = 0.0

    output = outputs.get("output")
    if output:
        doc_type = output.get("document_type", "unknown") or "unknown"
        confidence = output.get("classification_confidence", 0.0) or 0.0
        extracted = output.get("extracted")
        if extracted:
            extracted_data = extracted.get("raw", {}) or {}
        state_status = output.get("status")
        if state_status and state_status.lower() == "error":
            run_status = "error"
        elif output.get("error_message"):
            run_status = "error"

    start_time = run.get("start_time")
    end_time = run.get("end_time")
    duration_ms = 0
    if end_time and start_time:
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

    processed_at = None
    if start_time:
        processed_at = start_time.isoformat() if hasattr(start_time, "isoformat") else str(start_time)

    return {
        "run_id": run.get("id", ""),
        "file_name": file_name,
        "document_type": doc_type,
        "confidence": confidence,
        "status": run_status,
        "extracted_data": extracted_data,
        "duration_ms": duration_ms,
        "processed_at": processed_at,
    }


@router.get("/runs")
def get_runs(
    hours: int = Query(72, ge=1, le=720),
    username: Annotated[str, Depends(get_current_user)] = None,
):
    """Get LangSmith processing runs and aggregate token stats."""
    api_key = os.environ.get("LANGCHAIN_API_KEY")
    project_name = os.environ.get("LANGCHAIN_PROJECT", "document-processor")

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LangSmith not configured (LANGCHAIN_API_KEY missing)",
        )

    from langsmith import Client

    client = Client(api_key=api_key)
    start_time = datetime.now(timezone.utc) - timedelta(hours=hours)

    runs_raw = list(
        client.list_runs(
            project_name=project_name,
            filter='eq(name, "process_file")',
            start_time=start_time,
            limit=100,
        )
    )

    serializable = [
        {
            "inputs": r.inputs,
            "outputs": r.outputs,
            "error": r.error,
            "start_time": r.start_time,
            "end_time": r.end_time,
            "id": str(r.id),
        }
        for r in runs_raw
        if r.outputs is not None or r.error is not None
    ]

    parsed = [_parse_run(r) for r in serializable]

    # Token stats from LLM runs
    llm_runs = list(
        client.list_runs(
            project_name=project_name,
            filter='eq(run_type, "llm")',
            start_time=start_time,
            limit=100,
        )
    )
    total_tokens = prompt_tokens = completion_tokens = 0
    for r in llm_runs:
        total = getattr(r, "total_tokens", 0) or 0
        prompt = getattr(r, "prompt_tokens", 0) or 0
        completion = getattr(r, "completion_tokens", 0) or 0
        extra = getattr(r, "extra", {}) or {}
        usage_meta = extra.get("usage_metadata", {})
        if usage_meta:
            total = total or usage_meta.get("total_tokens", 0)
            prompt = prompt or usage_meta.get("input_tokens", 0)
            completion = completion or usage_meta.get("output_tokens", 0)
        total_tokens += total
        prompt_tokens += prompt
        completion_tokens += completion

    return {
        "runs": parsed,
        "token_stats": {
            "total": total_tokens,
            "prompt": prompt_tokens,
            "completion": completion_tokens,
        },
    }


# ── Permanent history (Azure Table Storage) ───────────────────────────────────

@router.get("/history")
def get_history(
    months: int = Query(3, ge=1, le=24),
    top: int = Query(500, ge=1, le=2000),
    username: Annotated[str, Depends(get_current_user)] = None,
):
    """Get permanent processing history from Azure Table Storage."""
    from src.utils.table_storage import list_runs
    runs = list_runs(months=months, top=top)
    return {"runs": runs, "total": len(runs)}


# ── Azure Search documents ─────────────────────────────────────────────────────

@router.get("/documents")
def get_documents(
    top_k: int = Query(1000, ge=1, le=1000),
    username: Annotated[str, Depends(get_current_user)] = None,
):
    """List indexed documents from Azure AI Search."""
    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    index = os.environ.get("AZURE_SEARCH_INDEX", "processed-documents")
    api_key = os.environ.get("AZURE_SEARCH_API_KEY")

    if not all([endpoint, api_key]):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Azure Search not configured",
        )

    headers = {"api-key": api_key, "Content-Type": "application/json"}

    with httpx.Client(timeout=15) as client:
        count_url = f"{endpoint}/indexes/{index}/docs/$count?api-version=2024-07-01"
        count_resp = client.get(count_url, headers=headers)
        total_chunks = int(count_resp.text) if count_resp.status_code == 200 else 0

        search_url = f"{endpoint}/indexes/{index}/docs/search?api-version=2024-07-01"
        body = {
            "search": "*",
            "top": top_k,
            "select": "id,file_name,document_type,processed_at,extracted_data,image_urls",
            "orderby": "processed_at desc",
        }
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


# ── OneDrive upload ────────────────────────────────────────────────────────────

class UploadResult(BaseModel):
    name: str
    ok: bool
    error: str | None = None
    web_url: str | None = None


@router.post("/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    username: Annotated[str, Depends(get_current_user)] = None,
):
    """Upload PDF files to OneDrive /In folder for processing."""
    drive_id = os.environ.get("MS_GRAPH_DRIVE_ID")
    inbox_folder = os.environ.get("MS_GRAPH_INBOX_FOLDER", "/Document Processor/In")

    if not drive_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OneDrive not configured (MS_GRAPH_DRIVE_ID missing)",
        )

    from src.nodes.onedrive import upload_to_onedrive

    results: list[dict] = []
    for f in files:
        fname = f.filename or "unknown"
        if not fname.lower().endswith(".pdf"):
            results.append({"name": fname, "ok": False, "error": "Only PDF files accepted"})
            continue
        try:
            content = await f.read()
            meta = upload_to_onedrive(
                drive_id=drive_id,
                folder_path=inbox_folder,
                file_name=fname,
                file_content=content,
            )
            results.append({"name": fname, "ok": True, "web_url": meta.get("web_url")})
        except Exception as e:
            results.append({"name": fname, "ok": False, "error": str(e)})

    return {"results": results, "folder": inbox_folder}
