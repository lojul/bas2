"""Pipeline routes — file triage, processing, upload and OneDrive helpers."""

import asyncio
import json
import os
import threading
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from api.auth import get_current_user
from api.common import (
    SUPPORTED_FORMATS,
    get_drive_id,
    get_graph_token,
    patch_onedrive_env,
    read_config,
)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _file_exists_in_onedrive(drive_id: str, folder_path: str, file_name: str, token: str) -> bool:
    try:
        path = f"{folder_path.strip('/')}/{file_name}"
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{path}"
        with httpx.Client(timeout=10) as client:
            resp = client.get(url, headers={"Authorization": f"Bearer {token}"})
            return resp.status_code == 200
    except Exception:
        return False


def _state_to_result(state: Any) -> dict:
    from dataclasses import asdict
    from src.state import ProcessingStatus

    extracted: dict = {}
    if state.extracted:
        try:
            extracted = asdict(state.extracted).get("raw", {})
        except Exception:
            extracted = {}

    doc_type = state.document_type.value if state.document_type else "unknown"

    if not extracted and state.index_id:
        try:
            from src.nodes.indexer import get_existing_document
            indexed = get_existing_document(state.index_id)
            if indexed:
                extracted = json.loads(indexed.get("extracted_data", "{}") or "{}")
                if doc_type == "unknown" and indexed.get("document_type"):
                    doc_type = indexed["document_type"]
        except Exception:
            pass

    return {
        "file_name": state.file_name,
        "document_type": doc_type,
        "confidence": state.classification_confidence,
        "status": "error" if state.status == ProcessingStatus.ERROR else "success",
        "pages": state.ocr.pages if state.ocr else 0,
        "tables": len(state.ocr.tables) if state.ocr else 0,
        "extracted_data": extracted,
        "error": state.error_message if state.status == ProcessingStatus.ERROR else None,
        "index_id": state.index_id,
        "odoo_record_id": state.odoo_record_id or None,
        "odoo_sync_status": state.odoo_sync_status or None,
    }


# ── Triage ─────────────────────────────────────────────────────────────────────

@router.post("/triage")
async def triage_file(
    file: UploadFile = File(...),
    username: Annotated[str, Depends(get_current_user)] = None,
):
    """Quick scan: detect document type and whether it can be processed."""
    fname = file.filename or "unknown"
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""

    if ext not in SUPPORTED_FORMATS:
        from src.utils.table_storage import log_unsupported
        log_unsupported(fname, ext)
        return {
            "file_name": fname,
            "can_process": False,
            "detected_type": "unsupported",
            "format": ext or "unknown",
            "confidence": 0.0,
            "reason": f".{ext} files are not yet supported" if ext else "Unknown file type",
        }

    content = await file.read()

    try:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
        from azure.core.credentials import AzureKeyCredential

        di_endpoint = os.environ.get("AZURE_DOC_INTEL_ENDPOINT", "")
        di_key = os.environ.get("AZURE_DOC_INTEL_KEY", "")
        if not di_endpoint or not di_key:
            raise ValueError("Azure Document Intelligence not configured")

        di_client = DocumentIntelligenceClient(endpoint=di_endpoint, credential=AzureKeyCredential(di_key))
        analyze_request = AnalyzeDocumentRequest(bytes_source=content)
        # pages is a query param on begin_analyze_document, not a field on AnalyzeDocumentRequest
        if ext == "pdf":
            poller = di_client.begin_analyze_document("prebuilt-read", analyze_request, pages="1-2")
        else:
            poller = di_client.begin_analyze_document("prebuilt-read", analyze_request)
        di_result = poller.result()
        text = di_result.content or ""
        page_count = len(di_result.pages) if di_result.pages else 1

    except Exception as e:
        return {
            "file_name": fname,
            "can_process": True,
            "detected_type": "unknown",
            "format": ext,
            "confidence": 0.0,
            "reason": f"OCR unavailable: {str(e)[:80]}",
        }

    try:
        from src.nodes.classifier import call_llm
        clf = call_llm(text[:3000], page_count, len(text), 0)
        doc_type = clf.get("type", "unknown")
        confidence = float(clf.get("confidence", 0.5))
    except Exception:
        doc_type = "unknown"
        confidence = 0.0

    # Filename-based override: strong brochure/deck keywords always win over
    # the LLM classifier. Filenames are reliable; classifier can misread sparse
    # image-heavy PDFs as "listing" when the first 2 pages contain property specs.
    word_count = len(text.split())
    name_lower = fname.lower()
    if any(kw in name_lower for kw in ("brochure", "deck", "pre-leasing", "preleasing", "prospectus", "marketing")):
        doc_type = "pitching_deck"
        confidence = max(confidence, 0.7)

    # Predict which extraction path the pipeline will use (mirrors analyzer.py logic).
    # Use 800 words as threshold — first 2 pages of a pure image brochure rarely
    # yields that much text from DI even counting headers/footers.
    if doc_type == "pitching_deck" and word_count < 800:
        extraction_path = "vision"
    elif doc_type == "listing_list":
        extraction_path = "conversational"
    else:
        extraction_path = "structured"

    # ocr_complete = True when triage processed the full file (so process can skip DI)
    # PDFs are capped at pages 1-2 in triage; only single-page PDFs are fully covered.
    ocr_complete = (ext != "pdf") or (page_count == 1)

    return {
        "file_name": fname,
        "can_process": True,
        "detected_type": doc_type,
        "format": ext,
        "confidence": confidence,
        "reason": None,
        "ocr_text": text,
        "ocr_pages": page_count,
        "ocr_complete": ocr_complete,
        "extraction_path": extraction_path,
    }


# ── Process ────────────────────────────────────────────────────────────────────

@router.post("/process")
async def process_file(
    file: UploadFile = File(...),
    ocr_text: str | None = Form(default=None),
    ocr_pages: int = Form(default=0),
    ocr_complete: bool = Form(default=False),
    username: Annotated[str, Depends(get_current_user)] = None,
):
    """Run the full pipeline (OCR → classify → extract → index) on an uploaded file.

    Returns an SSE stream so Azure's 60s idle proxy timeout never triggers.
    Sends a heartbeat comment every 15s while the pipeline runs, then the JSON result.

    If ocr_text + ocr_complete are provided (from a prior triage call that already
    processed the full file), DI is skipped and the pre-computed text is used directly.
    """
    fname = file.filename or "unknown"
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if ext not in SUPPORTED_FORMATS:
        raise HTTPException(status_code=400, detail=f".{ext} files are not supported")

    content = await file.read()

    precomputed_ocr = None
    if ocr_text and ocr_complete:
        from src.state import OCRResult
        precomputed_ocr = OCRResult(text=ocr_text, pages=ocr_pages or 1, confidence=0.97)

    result_holder: dict = {}
    done_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _run_pipeline():
        try:
            from src.graph import process_file_from_bytes
            state = process_file_from_bytes(content, fname, "dashboard", precomputed_ocr)
            result_holder["result"] = _state_to_result(state)
        except Exception as e:
            try:
                from src.utils.table_storage import log_run
                log_run(file_name=fname, document_type="unknown", status="error", duration_ms=0, error_message=str(e))
            except Exception:
                pass
            result_holder["result"] = {
                "file_name": fname, "status": "error", "error": str(e),
                "document_type": "unknown", "confidence": 0,
                "pages": 0, "tables": 0, "extracted_data": {}, "index_id": None,
            }
        finally:
            loop.call_soon_threadsafe(done_event.set)

    async def _stream():
        thread = threading.Thread(target=_run_pipeline, daemon=True)
        thread.start()

        while True:
            try:
                await asyncio.wait_for(done_event.wait(), timeout=15.0)
                break
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"

        result = result_holder.get("result", {
            "file_name": fname, "status": "error", "error": "Pipeline did not return a result",
            "document_type": "unknown", "confidence": 0,
            "pages": 0, "tables": 0, "extracted_data": {}, "index_id": None,
        })
        yield f"data: {json.dumps({'results': [result]})}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Upload ─────────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    folder_path: str | None = Form(default=None),
    drive_id: str | None = Form(default=None),
    username: Annotated[str, Depends(get_current_user)] = None,
):
    """Upload files to a OneDrive folder (defaults to configured inbox)."""
    effective_drive_id = drive_id or os.environ.get("MS_GRAPH_DRIVE_ID")
    cfg = read_config()
    default_inbox = os.environ.get("MS_GRAPH_INBOX_FOLDER") or cfg.get("inbox_folder", "/Document Processor/In")
    target_folder = folder_path.strip() if folder_path and folder_path.strip() else default_inbox

    if not effective_drive_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OneDrive not configured (MS_GRAPH_DRIVE_ID missing)",
        )

    patch_onedrive_env()
    from src.nodes.onedrive import ensure_folder_exists, upload_to_onedrive

    try:
        ensure_folder_exists(effective_drive_id, target_folder)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not create OneDrive folder '{target_folder}': {e}",
        )

    results: list[dict] = []
    for f in files:
        fname = f.filename or "unknown"
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        if ext not in SUPPORTED_FORMATS:
            results.append({"name": fname, "ok": False, "error": f".{ext} not supported"})
            continue
        try:
            file_content = await f.read()
            meta = upload_to_onedrive(
                drive_id=effective_drive_id,
                folder_path=target_folder,
                file_name=fname,
                file_content=file_content,
            )
            results.append({"name": fname, "ok": True, "web_url": meta.get("web_url")})
        except Exception as e:
            results.append({"name": fname, "ok": False, "error": str(e)})

    return {"results": results, "folder": target_folder}


# ── Check (index + OneDrive) ───────────────────────────────────────────────────

@router.get("/check")
def check_file(
    file_name: str = Query(...),
    username: Annotated[str, Depends(get_current_user)] = None,
):
    """Check if a file is already indexed in Azure AI Search."""
    import hashlib

    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    index = os.environ.get("AZURE_SEARCH_INDEX", "processed-documents")
    api_key = os.environ.get("AZURE_SEARCH_API_KEY")

    if not all([endpoint, api_key]):
        return {"exists": False}

    doc_id = hashlib.md5(file_name.encode()).hexdigest()
    headers = {"api-key": api_key}
    lookup_url = (
        f"{endpoint}/indexes/{index}/docs/{doc_id}"
        "?api-version=2024-07-01"
        "&$select=id,file_name,document_type,processed_at,extracted_data"
    )

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(lookup_url, headers=headers)
            if resp.status_code == 404:
                return {"exists": False}
            if resp.status_code != 200:
                return {"exists": False}
            doc = resp.json()
    except Exception:
        return {"exists": False}

    extracted_raw = doc.get("extracted_data")
    if isinstance(extracted_raw, str):
        try:
            extracted_raw = json.loads(extracted_raw)
        except Exception:
            extracted_raw = {}

    return {
        "exists": True,
        "document_type": doc.get("document_type", "unknown"),
        "processed_at": doc.get("processed_at"),
        "extracted_data": extracted_raw or {},
    }


@router.get("/onedrive-check")
async def onedrive_check_file(
    file_name: str = Query(...),
    username: Annotated[str, Depends(get_current_user)] = None,
):
    """Check if a file exists in the OneDrive inbox or processed folder."""
    drive_id = get_drive_id()
    if not drive_id:
        return {"drive_configured": False}

    try:
        token = get_graph_token()
    except Exception:
        return {"drive_configured": False}

    cfg = read_config()
    inbox_folder = os.environ.get("MS_GRAPH_INBOX_FOLDER") or cfg.get("inbox_folder", "/Document Processor/In")
    parent = inbox_folder.rsplit("/", 1)[0] or "/"
    processed_folder = f"{parent}/Processed"

    loop = asyncio.get_event_loop()
    in_inbox, in_processed = await asyncio.gather(
        loop.run_in_executor(None, lambda: _file_exists_in_onedrive(drive_id, inbox_folder, file_name, token)),
        loop.run_in_executor(None, lambda: _file_exists_in_onedrive(drive_id, processed_folder, file_name, token)),
    )

    return {
        "drive_configured": True,
        "in_inbox": in_inbox,
        "in_processed": in_processed,
        "inbox_folder": inbox_folder,
        "processed_folder": processed_folder,
    }


# ── OneDrive browser ───────────────────────────────────────────────────────────

@router.get("/onedrive-drives")
async def list_onedrive_drives(
    username: Annotated[str, Depends(get_current_user)] = None,
):
    """List all OneDrive / SharePoint drives accessible to the service principal."""
    default_drive_id = get_drive_id()
    if not default_drive_id:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OneDrive not configured")

    try:
        token = get_graph_token()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    drives: list[dict] = []
    with httpx.Client(timeout=15) as client:
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.get(f"https://graph.microsoft.com/v1.0/drives/{default_drive_id}", headers=headers)
        if resp.status_code == 200:
            d = resp.json()
            drives.append({"id": d["id"], "name": d.get("name", "OneDrive"), "type": d.get("driveType", ""), "is_default": True})

        existing_ids = {d["id"] for d in drives}

        try:
            users_resp = client.get(
                "https://graph.microsoft.com/v1.0/users?$select=id,displayName,mail&$top=50", headers=headers
            )
            if users_resp.status_code == 200:
                for user in users_resp.json().get("value", []):
                    mail = user.get("mail", "") or ""
                    if not mail or "@" not in mail:
                        continue
                    dr_resp = client.get(f"https://graph.microsoft.com/v1.0/users/{user['id']}/drive", headers=headers)
                    if dr_resp.status_code == 200:
                        d = dr_resp.json()
                        if d["id"] not in existing_ids:
                            drives.append({"id": d["id"], "name": f"{user.get('displayName', mail)} (OneDrive)", "type": d.get("driveType", "business"), "is_default": False})
                            existing_ids.add(d["id"])
        except Exception:
            pass

        try:
            sites_resp = client.get(
                "https://graph.microsoft.com/v1.0/sites?search=*&$select=id,displayName&$top=20", headers=headers
            )
            if sites_resp.status_code == 200:
                for site in sites_resp.json().get("value", []):
                    dr_resp = client.get(f"https://graph.microsoft.com/v1.0/sites/{site['id']}/drives", headers=headers)
                    if dr_resp.status_code == 200:
                        for d in dr_resp.json().get("value", []):
                            if d["id"] not in existing_ids:
                                drives.append({"id": d["id"], "name": f"{site.get('displayName', 'Site')} / {d.get('name', 'Documents')}", "type": d.get("driveType", "documentLibrary"), "is_default": False})
                                existing_ids.add(d["id"])
        except Exception:
            pass

    return {"drives": drives}


@router.get("/onedrive-folders")
async def list_onedrive_folders(
    path: str = Query(default="/"),
    drive_id: str | None = Query(default=None),
    username: Annotated[str, Depends(get_current_user)] = None,
):
    """List immediate child folders at a given OneDrive path."""
    effective_drive_id = drive_id or get_drive_id()
    if not effective_drive_id:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OneDrive not configured")

    try:
        token = get_graph_token()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    clean = path.strip()
    if not clean or clean == "/":
        url = f"https://graph.microsoft.com/v1.0/drives/{effective_drive_id}/root/children"
    else:
        encoded = clean.strip("/")
        url = f"https://graph.microsoft.com/v1.0/drives/{effective_drive_id}/root:/{encoded}:/children"

    with httpx.Client(timeout=15) as client:
        resp = client.get(url, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code == 404:
            return {"folders": [], "path": clean or "/"}
        resp.raise_for_status()
        data = resp.json()

    folders = []
    for item in data.get("value", []):
        if "folder" in item:
            parent = clean.rstrip("/") if clean and clean != "/" else ""
            folders.append({"name": item["name"], "path": f"{parent}/{item['name']}"})

    folders.sort(key=lambda f: f["name"].lower())
    return {"folders": folders, "path": clean or "/"}
