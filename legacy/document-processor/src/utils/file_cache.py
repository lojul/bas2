"""Blob-backed pending-file cache for the AI assistant.

Survives process restarts and multi-worker scale-out (the in-process dict it
replaces lost pending files on every deploy, breaking "3"/"yes" confirmations).
Falls back to in-memory when blob storage is not configured.
"""

import base64
import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_CONTAINER = "assistant-file-cache"
_TTL_MINUTES = 30

# In-memory first-level cache: key = f"{user_id}:{channel}"
_MEMORY: dict[str, tuple[str, bytes, datetime]] = {}
_MAX_MEMORY = 50


def _container_client():
    from azure.storage.blob import BlobServiceClient

    account = os.environ.get("AZURE_BLOB_ACCOUNT", "")
    sas = os.environ.get("AZURE_BLOB_WRITE_SAS", "")
    if not account or not sas:
        return None
    client = BlobServiceClient(f"https://{account}.blob.core.windows.net", credential=sas)
    container = client.get_container_client(_CONTAINER)
    try:
        if not container.exists():
            container.create_container()  # private — file contents are client data
    except Exception:
        pass
    return container


def _blob_name(user_id: str, channel: str) -> str:
    safe = "".join(c if c.isalnum() or c in "+-_." else "-" for c in user_id)
    return f"{channel}/{safe}"


def cache_file(user_id: str, channel: str, file_name: str, file_bytes: bytes) -> None:
    """Store the user's pending file (memory + blob)."""
    key = f"{user_id}:{channel}"
    _MEMORY[key] = (file_name, file_bytes, datetime.now(timezone.utc))
    if len(_MEMORY) > _MAX_MEMORY:
        del _MEMORY[next(iter(_MEMORY))]

    try:
        container = _container_client()
        if container is None:
            return
        blob = container.get_blob_client(_blob_name(user_id, channel))
        # Blob metadata must be ASCII — base64-encode the filename
        encoded_name = base64.b64encode(file_name.encode("utf-8")).decode("ascii")
        blob.upload_blob(file_bytes, overwrite=True, metadata={"filename_b64": encoded_name})
    except Exception as e:
        logger.warning("file_cache: blob write failed (%s) — memory-only", e)


def get_cached_file(user_id: str, channel: str) -> tuple[str, bytes] | None:
    """Return (file_name, file_bytes) if a non-expired pending file exists."""
    key = f"{user_id}:{channel}"
    now = datetime.now(timezone.utc)

    entry = _MEMORY.get(key)
    if entry:
        file_name, file_bytes, cached_at = entry
        if now - cached_at < timedelta(minutes=_TTL_MINUTES):
            return file_name, file_bytes
        _MEMORY.pop(key, None)

    try:
        container = _container_client()
        if container is None:
            return None
        blob = container.get_blob_client(_blob_name(user_id, channel))
        props = blob.get_blob_properties()
        if now - props.last_modified > timedelta(minutes=_TTL_MINUTES):
            return None
        encoded_name = (props.metadata or {}).get("filename_b64", "")
        file_name = (
            base64.b64decode(encoded_name).decode("utf-8") if encoded_name else "attachment.bin"
        )
        file_bytes = blob.download_blob().readall()
        _MEMORY[key] = (file_name, file_bytes, props.last_modified)
        return file_name, file_bytes
    except Exception:
        return None


def clear_cached_file(user_id: str, channel: str) -> None:
    """Remove the pending file for this user+channel."""
    _MEMORY.pop(f"{user_id}:{channel}", None)
    try:
        container = _container_client()
        if container is not None:
            container.get_blob_client(_blob_name(user_id, channel)).delete_blob()
    except Exception:
        pass
