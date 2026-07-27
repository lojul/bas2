"""Durable pipeline job queue (Azure Storage Queue + Blob).

The assistant enqueues jobs here instead of running them in a daemon thread —
threads die silently when the App Service worker recycles (deploys, idle
recycling), losing the job and the user notification. The Function App
consumes the queue, giving retry and poison-queue handling for free.

Message flow:
  App Service: file bytes → blob "pipeline-jobs/{uuid}" ; JSON message → queue
  Function App: queue trigger → run_pipeline_job(payload) → WhatsApp notify

All heavy imports (graph, fitz) are lazy — this module is imported by API
routes at startup, which must never load PyMuPDF.
"""

import base64
import json
import logging
import os
import uuid

logger = logging.getLogger(__name__)

QUEUE_NAME = "pipeline-jobs"
_JOB_CONTAINER = "pipeline-jobs"

_TYPE_LABELS = {
    "news": "知識文章（市場資訊）",
    "listing": "物業盤源（單一物業）",
    "listing_list": "物業盤源（多個物業）",
    "pitching_deck": "物業盤源（樓書/推廣冊）",
    "contact": "名片/聯絡人",
    "unknown": "未能分類",
}


def format_completion(final) -> str:
    """Build the WhatsApp completion notification from the final pipeline state."""
    from src.nodes.knowledge_writer import ODOO_URL
    from src.state import ProcessingStatus

    doc_type = final.document_type.value if final.document_type else "unknown"
    label = _TYPE_LABELS.get(doc_type, doc_type)

    if final.status == ProcessingStatus.ERROR:
        return f"❌ 處理失敗：{final.file_name}\n原因：{(final.error_message or '未知錯誤')[:120]}"

    lines = [f"✅ 處理完成：{final.file_name}", f"分類：{label}"]

    if final.odoo_sync_status == "synced" and final.odoo_record_id:
        if doc_type == "news":
            lines.append(f"知識文章已建立：\n{ODOO_URL}/knowledge/article/{final.odoo_record_id}")
        elif doc_type == "contact":
            # Show extracted contact fields so user can verify what was saved
            raw = final.extracted.raw if final.extracted else {}
            name = raw.get("name_zh") or raw.get("name") or ""
            company = raw.get("company_zh") or raw.get("company") or ""
            phone = raw.get("phone") or raw.get("mobile") or ""
            email = raw.get("email") or ""
            detail_parts = [p for p in (name, company, phone, email) if p]
            if detail_parts:
                lines.append("\n".join(detail_parts))
            lines.append(f"Odoo 聯絡人已建立/更新：\n{ODOO_URL}/odoo/contacts/{final.odoo_record_id}")
        else:
            ids = final.odoo_record_id.split(",")
            lines.append(f"Odoo 放盤管理已建立/更新 {len(ids)} 筆記錄（ID: {final.odoo_record_id}）")
    elif final.odoo_sync_status == "duplicate":
        lines.append(f"⚠️ Odoo 中已有相同文章（未重複建立）：\n{ODOO_URL}/knowledge/article/{final.odoo_record_id}")
    elif final.odoo_sync_status == "error":
        detail = f"：{final.odoo_error_detail[:150]}" if getattr(final, "odoo_error_detail", "") else ""
        lines.append(f"⚠️ Odoo 同步失敗（文件已索引，可稍後重試）{detail}")

    if final.index_id:
        if doc_type == "contact":
            lines.append("已索引至搜尋庫 — 可透過聯絡人查詢（6）搜尋")
        else:
            lines.append("已索引至搜尋庫 — 可透過物業查詢（4）搜尋")

    return "\n".join(lines)


def _queue_client():
    from azure.storage.queue import QueueClient, TextBase64EncodePolicy

    conn = os.environ.get("PIPELINE_QUEUE_CONN", "") or os.environ.get("AzureWebJobsStorage", "")
    if not conn:
        return None
    return QueueClient.from_connection_string(
        conn, QUEUE_NAME, message_encode_policy=TextBase64EncodePolicy()
    )


def _blob_container():
    from azure.storage.blob import BlobServiceClient

    account = os.environ.get("AZURE_BLOB_ACCOUNT", "")
    sas = os.environ.get("AZURE_BLOB_WRITE_SAS", "")
    if not account or not sas:
        return None
    client = BlobServiceClient(f"https://{account}.blob.core.windows.net", credential=sas)
    container = client.get_container_client(_JOB_CONTAINER)
    try:
        if not container.exists():
            container.create_container()
    except Exception:
        pass
    return container


def enqueue_pipeline_job(
    file_bytes: bytes | None,
    file_name: str | None,
    text: str = "",
    forced_type=None,
    skip_duplicate_check: bool = False,
    notify_user: str | None = None,
    notify_channel: str = "",
    sender_number: str = "",
) -> bool:
    """Persist the job and enqueue it. Returns False if queue is unavailable
    (caller should fall back to in-process execution)."""
    try:
        queue = _queue_client()
        if queue is None:
            return False

        blob_name = ""
        if file_bytes and file_name:
            container = _blob_container()
            if container is None:
                return False
            blob_name = f"{uuid.uuid4().hex}"
            container.get_blob_client(blob_name).upload_blob(file_bytes, overwrite=True)

        payload = {
            "blob_name": blob_name,
            "file_name": file_name or "",
            "text": text,
            "forced_type": forced_type.value if forced_type else None,
            "skip_duplicate_check": skip_duplicate_check,
            "notify_user": notify_user or "",
            "notify_channel": notify_channel,
            "sender_number": sender_number,
        }
        try:
            queue.create_queue()
        except Exception:
            pass  # already exists
        queue.send_message(json.dumps(payload, ensure_ascii=False))
        logger.info("Enqueued pipeline job for '%s'", file_name or "text")
        return True
    except Exception as e:
        logger.warning("enqueue_pipeline_job failed (%s) — falling back to thread", e)
        return False


_poison_alerted: set[str] = set()


def check_poison_queue() -> int:
    """Alert the admin on WhatsApp if failed jobs are sitting in the poison queue.

    Called from the Function App timer. Returns the poison message count.
    Alerts at most once per day per process.
    """
    from datetime import datetime, timezone

    try:
        from azure.storage.queue import QueueClient

        conn = os.environ.get("PIPELINE_QUEUE_CONN", "") or os.environ.get("AzureWebJobsStorage", "")
        if not conn:
            return 0
        poison = QueueClient.from_connection_string(conn, f"{QUEUE_NAME}-poison")
        props = poison.get_queue_properties()
        count = props.approximate_message_count or 0
    except Exception:
        return 0  # poison queue doesn't exist yet = no failures

    if count > 0:
        logger.error("Poison queue has %d failed pipeline job(s)", count)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        admin = os.environ.get("ADMIN_WHATSAPP", "")
        if admin and today not in _poison_alerted:
            _poison_alerted.add(today)
            from src.utils.whatsapp_notify import send_whatsapp
            send_whatsapp(
                admin,
                f"⚠️ 有 {count} 個文件處理工作失敗（已重試 5 次仍失敗）。\n"
                f"請檢查 Azure Storage Queue「{QUEUE_NAME}-poison」了解詳情。",
            )
    return count


def run_pipeline_job(payload: dict) -> None:
    """Execute one queued job: download bytes, run pipeline, notify user.

    Called by the Function App queue trigger. Raising lets the Functions
    runtime retry (5 attempts, then poison queue).
    """
    from src.graph import process_file_from_bytes
    from src.state import DocumentType, OCRResult

    blob_name = payload.get("blob_name", "")
    file_name = payload.get("file_name", "")
    text = payload.get("text") or ""
    # Guard: text is the filename echoed by Twilio — treat as no content so DI runs
    import urllib.parse
    if text and urllib.parse.unquote_plus(file_name) == text:
        text = ""
    forced_raw = payload.get("forced_type")
    forced_type = DocumentType(forced_raw) if forced_raw else None
    skip_dup = bool(payload.get("skip_duplicate_check"))
    notify_user = payload.get("notify_user", "")
    notify_channel = payload.get("notify_channel", "")
    sender_number = payload.get("sender_number", "")

    try:
        if blob_name:
            container = _blob_container()
            file_bytes = container.get_blob_client(blob_name).download_blob().readall()
            # Forwarded posts arrive as image + full article text — the text IS the
            # content. Use it as precomputed OCR (skips Azure DI; image kept for Odoo).
            pre_ocr = OCRResult(text=text) if text and len(text.strip()) >= 60 else None
            final = process_file_from_bytes(
                file_bytes, file_name, "assistant",
                precomputed_ocr=pre_ocr,
                forced_type=forced_type, skip_duplicate_check=skip_dup,
                whatsapp_number=sender_number,
            )
            try:
                container.get_blob_client(blob_name).delete_blob()
            except Exception:
                pass
        else:
            from datetime import datetime, timezone
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            final = process_file_from_bytes(
                text.encode("utf-8"), f"whatsapp-news-{stamp}.txt", "assistant",
                precomputed_ocr=OCRResult(text=text),
                forced_type=forced_type, skip_duplicate_check=skip_dup,
                whatsapp_number=sender_number,
            )
        message = format_completion(final)
    except Exception as e:
        logger.error("Pipeline job failed for '%s': %s", file_name, e)
        message = f"❌ 處理失敗：{file_name or '文字內容'}\n原因：{str(e)[:120]}"

    if notify_user and notify_channel == "whatsapp":
        from src.utils.whatsapp_notify import send_whatsapp
        send_whatsapp(notify_user, message)
