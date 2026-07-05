"""Azure Table Storage — AI assistant session persistence.

Falls back to in-memory store when AZURE_TABLE_SAS is not configured.
In-memory store persists across requests within a single process but resets on restart.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_ACCOUNT = "blobhk04472"
_TABLE = "AssistantSessions"
_TTL_MINUTES = 30

# In-memory fallback: key = (channel, safe_user_id)
_MEMORY: dict[tuple[str, str], dict] = {}


_table_ensured = False


def _client():
    from azure.data.tables import TableServiceClient
    global _table_ensured
    sas = os.environ.get("AZURE_TABLE_SAS", "")
    if not sas:
        return None
    url = f"https://{_ACCOUNT}.table.core.windows.net/?{sas}"
    service = TableServiceClient(endpoint=url)
    if not _table_ensured:
        # Table was never created in production — sessions silently fell back to
        # memory-only and were lost on every restart (found 2026-07-05).
        try:
            service.create_table_if_not_exists(_TABLE)
            _table_ensured = True
        except Exception:
            pass
    return service.get_table_client(_TABLE)


def _safe_key(user_id: str) -> str:
    """Sanitise user_id for Table Storage row key (no /, \\, #, ?)."""
    for ch in "/\\#?":
        user_id = user_id.replace(ch, "-")
    return user_id[:512]


def _default_session() -> dict:
    return {"state": "idle", "route": None, "messages": [], "pending": {}}


def get_session(user_id: str, channel: str) -> dict:
    """Load session. Returns fresh idle session if not found or expired."""
    key = (channel, _safe_key(user_id))
    try:
        client = _client()
        if client is None:
            # In-memory fallback
            entry = _MEMORY.get(key)
            if entry:
                updated = entry.get("updated_at")
                if updated and (datetime.now(timezone.utc) - updated) < timedelta(minutes=_TTL_MINUTES):
                    return {k: v for k, v in entry.items() if k != "updated_at"}
            return _default_session()

        entity = client.get_entity(partition_key=channel, row_key=_safe_key(user_id))

        updated_raw = entity.get("updated_at", "")
        if updated_raw:
            updated = datetime.fromisoformat(updated_raw)
            if not updated.tzinfo:
                updated = updated.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - updated) > timedelta(minutes=_TTL_MINUTES):
                return _default_session()

        return {
            "state": entity.get("state", "idle"),
            "route": entity.get("route") or None,
            "messages": json.loads(entity.get("messages", "[]")),
            "pending": json.loads(entity.get("pending", "{}")),
        }
    except Exception:
        return _MEMORY.get(key) or _default_session()


def save_session(user_id: str, channel: str, session: dict) -> None:
    """Persist session to Azure Table Storage, with in-memory fallback."""
    key = (channel, _safe_key(user_id))
    # Always update in-memory store
    _MEMORY[key] = {**session, "updated_at": datetime.now(timezone.utc)}

    try:
        client = _client()
        if client is None:
            return

        entity = {
            "PartitionKey": channel,
            "RowKey": _safe_key(user_id),
            "state": session.get("state", "idle"),
            "route": session.get("route") or "",
            "messages": json.dumps(session.get("messages", [])[-10:], ensure_ascii=False),
            "pending": json.dumps(session.get("pending", {}), ensure_ascii=False),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        client.upsert_entity(entity)
    except Exception as e:
        logger.warning("Failed to save assistant session to Table Storage: %s", e)


def clear_session(user_id: str, channel: str) -> None:
    """Reset session to idle state."""
    key = (channel, _safe_key(user_id))
    _MEMORY.pop(key, None)
    save_session(user_id, channel, _default_session())
