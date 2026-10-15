"""Odoo 放盤管理 → 文件上傳 webhook — see src/utils/odoo_upload.py."""

import hmac
import logging
import os

from fastapi import APIRouter, HTTPException, Query, Request, status
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/odoo", tags=["odoo"])


@router.post("/upload")
async def odoo_upload(request: Request, token: str = Query(default="")):
    """Called by the Odoo automation rule with the upload record's id.

    Odoo Studio webhooks can't send custom headers, so the shared secret is in
    the URL (?token=...). Fails closed if ODOO_UPLOAD_WEBHOOK_TOKEN is unset.
    """
    from src.utils import odoo_upload as ou

    expected = os.environ.get("ODOO_UPLOAD_WEBHOOK_TOKEN", "")
    if not expected or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    try:
        payload = await request.json()
    except Exception:
        payload = {}
    model = payload.get("_model")
    if model and model != ou.UPLOAD_MODEL:
        raise HTTPException(status_code=400, detail=f"Unexpected model {model}")
    try:
        record_id = int(payload.get("_id") or payload.get("id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Missing record id (_id)")

    try:
        upload = await run_in_threadpool(ou.fetch_upload, record_id)
    except ou.OdooUploadError as e:
        logger.warning("Odoo upload %s rejected: %s", record_id, e)
        try:
            await run_in_threadpool(ou.set_status, record_id, ou.STATUS_ERROR, f"❌ {e}")
        except Exception:
            pass
        return {"status": "error", "detail": str(e)}

    from src.state import DocumentType
    from src.utils.job_queue import enqueue_pipeline_job

    # Name the record after its file if the uploader left the name empty
    await run_in_threadpool(
        ou.set_status, record_id, ou.STATUS_PROCESSING, "",
        None, None if upload["has_name"] else upload["file_name"],
    )
    queued = await run_in_threadpool(
        lambda: enqueue_pipeline_job(
            upload["file_bytes"], upload["file_name"],
            forced_type=DocumentType(upload["doc_type"]) if upload["doc_type"] else None,
            skip_duplicate_check=upload["allow_duplicate"],
            notify_user=str(record_id),
            notify_channel="odoo",
            source="odoo",
        )
    )
    if not queued:
        await run_in_threadpool(ou.set_status, record_id, ou.STATUS_ERROR, "❌ 排隊失敗，請稍後按「重新處理」")
        raise HTTPException(status_code=503, detail="Pipeline queue unavailable")

    logger.info("Odoo upload %s queued: %s", record_id, upload["file_name"])
    return {"status": "queued", "file_name": upload["file_name"]}
