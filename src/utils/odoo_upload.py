"""Odoo 放盤管理 → 文件上傳 channel.

Staff upload a file on a Studio-built record in Odoo (model ODOO_UPLOAD_MODEL,
menu 放盤管理 → 文件上傳). An Odoo automation rule ("Send Webhook Notification",
on create) POSTs the record id to /api/odoo/upload; that route reads the file
back from Odoo with fetch_upload() and enqueues it on the same pipeline queue
every other channel uses (source="odoo"). When the job finishes, the queue
worker calls report_result() through channel_notify, which writes the status
and result back to the upload record.

The webhook never carries the file — the processor pulls it from Odoo itself,
so a forged call can only (re)process a file that is already in Odoo.

Model and field names are whatever Odoo Studio generated; override them with
the ODOO_UPLOAD_* env vars if they differ from the defaults below. Optional
fields (doc type, allow duplicate, result, listings) are skipped if missing.

Lightweight on purpose (xmlrpc only) — imported by an App Service route,
which must never load PyMuPDF or the graph.
"""

import base64
import logging
import os
import xmlrpc.client
from typing import Any

logger = logging.getLogger(__name__)

ODOO_URL = os.environ.get("ODOO_URL", "https://c21net.odoo.com")
ODOO_DB = os.environ.get("ODOO_DB", "c21net")
ODOO_USERNAME = os.environ.get("ODOO_USERNAME", "admin@c21net.com")

UPLOAD_MODEL = os.environ.get("ODOO_UPLOAD_MODEL", "x_c21_doc_upload")
F_FILE = os.environ.get("ODOO_UPLOAD_FIELD_FILE", "x_studio_file")
F_FILENAME = os.environ.get("ODOO_UPLOAD_FIELD_FILENAME", "x_studio_file_filename")
F_DOC_TYPE = os.environ.get("ODOO_UPLOAD_FIELD_DOC_TYPE", "x_studio_doc_type")
F_ALLOW_DUP = os.environ.get("ODOO_UPLOAD_FIELD_ALLOW_DUP", "x_studio_allow_duplicate")
F_STATUS = os.environ.get("ODOO_UPLOAD_FIELD_STATUS", "x_studio_status")
F_RESULT = os.environ.get("ODOO_UPLOAD_FIELD_RESULT", "x_studio_result")
F_LISTINGS = os.environ.get("ODOO_UPLOAD_FIELD_LISTINGS", "x_studio_listing_ids")

# Status options as staff see them in Odoo (selection labels), with the
# English key Studio may have used instead.
STATUS_PENDING = ("待處理", "pending")
STATUS_PROCESSING = ("處理中", "processing")
STATUS_DONE = ("完成", "done")
STATUS_ERROR = ("失敗", "error")

# Document-type labels → DocumentType value. Order matters: 放盤表 before 放盤.
_DOC_TYPE_KEYWORDS: list[tuple[str, str | None]] = [
    ("自動", None), ("auto", None),
    ("放盤表", "listing_list"), ("listing_list", "listing_list"),
    ("樓書", "pitching_deck"), ("pitching", "pitching_deck"),
    ("新聞", "news"), ("知識", "news"), ("news", "news"),
    ("名片", "contact"), ("聯絡", "contact"), ("contact", "contact"),
    ("放盤", "listing"), ("listing", "listing"),
]

_LISTING_TYPES = {"listing", "listing_list", "pitching_deck"}


class OdooUploadError(Exception):
    """The upload record can't be processed (missing, no file, ...)."""


def _connect() -> tuple[Any, int, str]:
    api_key = os.environ.get("ODOO_API_KEY", "")
    if not api_key:
        raise OdooUploadError("ODOO_API_KEY not set")
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USERNAME, api_key, {})
    if not uid:
        raise OdooUploadError("Odoo authentication failed — check ODOO_API_KEY")
    return xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object"), uid, api_key


def _fields(models: Any, uid: int, api_key: str) -> dict:
    return models.execute_kw(
        ODOO_DB, uid, api_key, UPLOAD_MODEL, "fields_get", [],
        {"attributes": ["type", "selection"]},
    )


def map_doc_type(value: Any, field_def: dict | None) -> str | None:
    """Turn the record's document-type value into a DocumentType value (None = auto)."""
    if not value:
        return None
    label = str(value)
    for key, lbl in (field_def or {}).get("selection") or []:
        if key == value:
            label = f"{key} {lbl}"
            break
    label = label.lower()
    for keyword, doc_type in _DOC_TYPE_KEYWORDS:
        if keyword in label:
            return doc_type
    return None


def status_value(status: tuple[str, str], field_def: dict | None) -> str:
    """Value to write for a status: the matching selection key, or the label for a text field."""
    label, key = status
    for sel_key, sel_label in (field_def or {}).get("selection") or []:
        if sel_label == label or sel_key in (label, key):
            return sel_key
    return label


def _guess_name(record_name: str, file_bytes: bytes) -> str:
    ext = "pdf"
    if file_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        ext = "png"
    elif file_bytes[:3] == b"\xff\xd8\xff":
        ext = "jpg"
    return f"{record_name or 'odoo-upload'}.{ext}"


def fetch_upload(record_id: int) -> dict:
    """Read the uploaded file and options from the Odoo upload record."""
    models, uid, api_key = _connect()
    fields = _fields(models, uid, api_key)
    wanted = [f for f in (F_FILE, F_FILENAME, F_DOC_TYPE, F_ALLOW_DUP) if f in fields]
    rows = models.execute_kw(
        ODOO_DB, uid, api_key, UPLOAD_MODEL, "read", [[record_id]],
        {"fields": wanted + ["x_name", "display_name"]},
    )
    if not rows:
        raise OdooUploadError(f"{UPLOAD_MODEL} record {record_id} not found")
    row = rows[0]
    if not row.get(F_FILE):
        raise OdooUploadError("沒有上傳檔案")
    file_bytes = base64.b64decode(row[F_FILE])
    return {
        "file_bytes": file_bytes,
        "file_name": row.get(F_FILENAME) or _guess_name(row.get("display_name") or "", file_bytes),
        "doc_type": map_doc_type(row.get(F_DOC_TYPE), fields.get(F_DOC_TYPE)),
        "allow_duplicate": bool(row.get(F_ALLOW_DUP)),
        "has_name": bool(row.get("x_name")),
    }


def set_status(record_id: int, status: tuple[str, str], message: str | None = None,
               listing_ids: list[int] | None = None, name: str | None = None) -> None:
    """Write status (and optionally result text, linked listings, record name) to the record."""
    models, uid, api_key = _connect()
    fields = _fields(models, uid, api_key)
    vals: dict[str, Any] = {}
    if F_STATUS in fields:
        vals[F_STATUS] = status_value(status, fields[F_STATUS])
    if message is not None and F_RESULT in fields:
        vals[F_RESULT] = message
    if listing_ids and F_LISTINGS in fields:
        vals[F_LISTINGS] = [(6, 0, listing_ids)]
    if name:
        vals["x_name"] = name
    if vals:
        models.execute_kw(ODOO_DB, uid, api_key, UPLOAD_MODEL, "write", [[record_id], vals])


def _post_chatter(record_id: int, message: str) -> None:
    """Post the first line of the result in the record's chatter, notifying the uploader.
    Best-effort: the Studio model only has a chatter if it was created with one."""
    try:
        models, uid, api_key = _connect()
        rows = models.execute_kw(ODOO_DB, uid, api_key, UPLOAD_MODEL, "read",
                                 [[record_id]], {"fields": ["create_uid"]})
        partner_ids: list[int] = []
        if rows and rows[0].get("create_uid"):
            users = models.execute_kw(ODOO_DB, uid, api_key, "res.users", "read",
                                      [[rows[0]["create_uid"][0]]], {"fields": ["partner_id"]})
            if users and users[0].get("partner_id"):
                partner_ids = [users[0]["partner_id"][0]]
        models.execute_kw(ODOO_DB, uid, api_key, UPLOAD_MODEL, "message_post", [[record_id]], {
            "body": message.splitlines()[0] if message else "",
            "message_type": "comment",
            "subtype_xmlid": "mail.mt_comment",
            "partner_ids": partner_ids,
        })
    except Exception as e:
        logger.warning("Odoo upload %s: chatter post failed (%s)", record_id, e)


def report_result(target: str, message: str, final=None) -> bool:
    """channel_notify sender for "odoo": target is the upload record id."""
    try:
        record_id = int(target)
    except (TypeError, ValueError):
        logger.error("Odoo upload: bad record id %r", target)
        return False

    failed = message.startswith("❌") or (final is not None and final.odoo_sync_status == "error")
    listing_ids: list[int] = []
    if final is not None and not failed and final.odoo_sync_status == "synced":
        doc_type = final.document_type.value if final.document_type else ""
        if doc_type in _LISTING_TYPES and final.odoo_record_id:
            listing_ids = [int(i) for i in final.odoo_record_id.split(",") if i.strip().isdigit()]

    try:
        set_status(record_id, STATUS_ERROR if failed else STATUS_DONE, message, listing_ids)
    except Exception as e:
        logger.error("Odoo upload %s: could not write result (%s)", record_id, e)
        return False
    _post_chatter(record_id, message)
    return True
