"""Persists the Microsoft Graph delta link for the OneDrive sync timer.

Same Azure Table Storage account as ProcessingHistory/DiUsage (AZURE_TABLE_SAS),
so no new credential is needed. Mirrors bas-stacks' onedrive-sync/state_store.py.
"""

import logging
import os

logger = logging.getLogger(__name__)

_ACCOUNT = "blobhk04472"
_TABLE = "OneDriveSyncState"
_PARTITION_KEY = "sync"
_ROW_KEY = "deltaLink"


def _client():
    from azure.data.tables import TableServiceClient

    sas = os.environ.get("AZURE_TABLE_SAS", "")
    if not sas:
        return None
    url = f"https://{_ACCOUNT}.table.core.windows.net/?{sas}"
    client = TableServiceClient(endpoint=url)
    try:
        client.create_table_if_not_exists(_TABLE)
    except Exception:
        pass
    return client.get_table_client(_TABLE)


def load_delta_link() -> str | None:
    """Returns the saved delta link, or None on first run / missing state."""
    try:
        client = _client()
        if client is None:
            return None
        entity = client.get_entity(partition_key=_PARTITION_KEY, row_key=_ROW_KEY)
        return entity.get("value") or None
    except Exception:
        return None


def load_delta_state() -> dict | None:
    """Returns {"value": ..., "timestamp": ...} for diagnostics, or None."""
    try:
        client = _client()
        if client is None:
            return None
        entity = client.get_entity(partition_key=_PARTITION_KEY, row_key=_ROW_KEY)
        return {"value": entity.get("value"), "timestamp": entity.metadata.get("timestamp")}
    except Exception:
        return None


def save_delta_link(delta_link: str) -> None:
    """Persist the new delta link. Refuses to persist an empty value — an
    empty token reads back as "no baseline" and would send the next run down
    the full-traversal path (re-OCRs the whole drive). Never let that happen
    silently."""
    if not delta_link or not delta_link.strip():
        raise ValueError("Refusing to persist an empty OneDrive delta link.")

    client = _client()
    if client is None:
        raise RuntimeError("AZURE_TABLE_SAS not set — cannot persist OneDrive delta link.")

    client.upsert_entity({
        "PartitionKey": _PARTITION_KEY,
        "RowKey": _ROW_KEY,
        "value": delta_link,
    })
    logger.info("OneDrive delta link saved.")


def delete_delta_link() -> None:
    """Manual escape hatch for re-baselining. Next run will hard-stop (no
    auto full re-sync) until a new baseline is established deliberately."""
    try:
        client = _client()
        if client is not None:
            client.delete_entity(partition_key=_PARTITION_KEY, row_key=_ROW_KEY)
            logger.warning("OneDrive delta link deleted — re-baseline before re-enabling the sync.")
    except Exception:
        pass  # already gone


_WATERMARK_ROW_KEY = "highWaterMark"


def load_watermark() -> str | None:
    """ISO timestamp of the newest file already handled, or None if unset."""
    try:
        client = _client()
        if client is None:
            return None
        return client.get_entity(partition_key=_PARTITION_KEY, row_key=_WATERMARK_ROW_KEY).get("value") or None
    except Exception:
        return None


def save_watermark(iso_timestamp: str) -> None:
    if not iso_timestamp or not iso_timestamp.strip():
        raise ValueError("Refusing to persist an empty OneDrive watermark.")
    client = _client()
    if client is None:
        raise RuntimeError("AZURE_TABLE_SAS not set — cannot persist OneDrive watermark.")
    client.upsert_entity({
        "PartitionKey": _PARTITION_KEY,
        "RowKey": _WATERMARK_ROW_KEY,
        "value": iso_timestamp,
    })
