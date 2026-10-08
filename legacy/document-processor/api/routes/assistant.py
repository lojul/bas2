"""AI Assistant route — channel-agnostic ingest conversation endpoint."""

import os
import re
from typing import Annotated
from urllib.parse import unquote_plus

import httpx
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status

from api.auth import get_current_user

router = APIRouter(prefix="/assistant", tags=["assistant"])


def _sanitize_filename(name: str) -> str:
    """Strip corrupted non-ASCII characters (shown as ?) left by Twilio/Node.js encoding.

    Twilio doesn't preserve non-ASCII filenames in media headers, so Chinese characters
    arrive as literal '?' from the WhatsApp path. Strip them and keep the ASCII parts.
    If too little is left to be meaningful (e.g. just "C"), fall back to a timestamp name.
    Dashboard uploads bypass this path entirely (browser sends proper UTF-8 multipart).
    """
    from datetime import datetime, timezone
    stem, _, ext = name.rpartition(".")
    if not stem:
        return name
    cleaned = re.sub(r"\?+", "", stem)         # remove ? clusters (lost Chinese chars)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)   # remove empty parens ()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_.")
    if len(cleaned) < 3:
        # Stem is too short to be meaningful — use a timestamp so "C.pdf" never happens
        cleaned = f"document-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    return f"{cleaned}.{ext}" if cleaned else name

_ASSISTANT_API_KEY = os.environ.get("ASSISTANT_API_KEY", "")


def _check_auth(
    authorization: str | None,
    x_api_key: str | None,
) -> bool:
    """Accept either JWT Bearer (dashboard) or X-Api-Key (n8n / external channels)."""
    if x_api_key and _ASSISTANT_API_KEY and x_api_key == _ASSISTANT_API_KEY:
        return True
    return False


@router.post("/message")
async def assistant_message(
    user_id: str = Form(..., description="Phone number, session token, or any stable user identifier"),
    body: str = Form(default="", description="Text message from the user"),
    channel: str = Form(default="dashboard", description="dashboard | whatsapp | ..."),
    media_url: str | None = Form(default=None, description="Twilio media URL (WhatsApp) or any downloadable file URL"),
    file_name_override: str | None = Form(default=None, description="Explicit filename (UTF-8 text) — bypasses Content-Disposition encoding issues"),
    file: UploadFile | None = File(default=None, description="Direct file upload (dashboard)"),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
    # JWT auth for dashboard (optional — falls back to API key)
    _jwt_user: str | None = Depends(lambda: None),
):
    """Single entry point for the AI assistant across all channels.

    Returns { reply: str } — plain text, ready to display or forward to WhatsApp.
    """
    # Auth: JWT Bearer (dashboard) OR X-Api-Key (n8n / WhatsApp)
    jwt_ok = False
    try:
        from jose import jwt as _jwt
        from api.auth import SECRET_KEY, ALGORITHM
        if authorization and authorization.startswith("Bearer "):
            payload = _jwt.decode(authorization[7:], SECRET_KEY, algorithms=[ALGORITHM])
            jwt_ok = bool(payload.get("sub"))
    except Exception:
        pass

    if not jwt_ok and not _check_auth(authorization, x_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    # Resolve file bytes: prefer direct upload, fall back to media_url download
    file_bytes: bytes | None = None
    file_name: str | None = None

    if file and file.filename:
        file_bytes = await file.read()
        # file_name_override comes as UTF-8 text field — use it when the binary
        # Content-Disposition header has corrupted non-ASCII chars (Node.js Latin-1 issue)
        raw_name = file_name_override or unquote_plus(file.filename)
        file_name = _sanitize_filename(raw_name)
    elif media_url:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(media_url)
                resp.raise_for_status()
                file_bytes = resp.content
                # Derive filename from URL or content-type
                content_type = resp.headers.get("content-type", "")
                ext_map = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}
                ext = ext_map.get(content_type.split(";")[0].strip(), "bin")
                raw_name = unquote_plus(media_url.split("/")[-1].split("?")[0]) or f"attachment.{ext}"
                file_name = _sanitize_filename(raw_name)
        except Exception:
            pass  # media_url download failure is non-fatal; agent will handle gracefully

    from src.nodes.assistant import handle_message
    reply = handle_message(
        user_id=user_id,
        body=body,
        channel=channel,
        file_bytes=file_bytes,
        file_name=file_name,
        media_url=media_url if not file_bytes else None,
    )

    return {"reply": reply}


@router.delete("/session/{user_id}")
async def clear_session(
    user_id: str,
    channel: str = "dashboard",
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
):
    """Reset a user's session to idle. Useful for testing or starting over."""
    jwt_ok = False
    try:
        from jose import jwt as _jwt
        from api.auth import SECRET_KEY, ALGORITHM
        if authorization and authorization.startswith("Bearer "):
            payload = _jwt.decode(authorization[7:], SECRET_KEY, algorithms=[ALGORITHM])
            jwt_ok = bool(payload.get("sub"))
    except Exception:
        pass

    if not jwt_ok and not _check_auth(authorization, x_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    from src.utils.session_storage import clear_session as _clear
    _clear(user_id, channel)
    from src.nodes.assistant import clear_file_cache
    clear_file_cache(user_id, channel)
    return {"ok": True}
