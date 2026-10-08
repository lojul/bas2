"""Azure Table Storage — Teams ConversationReference persistence.

Bot Framework's proactive messaging (sending a message outside a live turn,
e.g. the pipeline-completion notify that arrives 1-3 minutes after the user's
original message) requires resuming a conversation via the ConversationReference
captured on a prior inbound activity — there is no simple "send to this user ID"
API like WhatsApp/Slack have. This module stores that reference, keyed by the
same user_id handle_message() already uses for session/file-cache keying
(Teams' conversation.id, stable per user+bot pair in personal-scope chat).

Falls back to in-memory store when AZURE_TABLE_SAS is not configured, same as
session_storage.py.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

_ACCOUNT = "blobhk04472"
_TABLE = "TeamsConversations"
_PARTITION = "teams"

_MEMORY: dict[str, dict] = {}
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
        try:
            service.create_table_if_not_exists(_TABLE)
            _table_ensured = True
        except Exception:
            pass
    return service.get_table_client(_TABLE)


def _safe_key(user_id: str) -> str:
    for ch in "/\\#?":
        user_id = user_id.replace(ch, "-")
    return user_id[:512]


def save_conversation_reference(user_id: str, reference: dict) -> None:
    """Persist a Bot Framework ConversationReference (as a plain dict) for user_id."""
    key = _safe_key(user_id)
    _MEMORY[key] = reference
    try:
        client = _client()
        if client is None:
            return
        client.upsert_entity({
            "PartitionKey": _PARTITION,
            "RowKey": key,
            "reference": json.dumps(reference, ensure_ascii=False),
        })
    except Exception as e:
        logger.warning("Failed to save Teams conversation reference: %s", e)


def get_conversation_reference(user_id: str) -> dict | None:
    """Load a previously saved ConversationReference dict, or None."""
    key = _safe_key(user_id)
    try:
        client = _client()
        if client is None:
            return _MEMORY.get(key)
        entity = client.get_entity(partition_key=_PARTITION, row_key=key)
        return json.loads(entity.get("reference", "{}")) or None
    except Exception:
        return _MEMORY.get(key)
