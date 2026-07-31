"""Daily usage limiting — per-user AND a global backstop.

Per-user cap alone isn't a real security boundary: if the channel API key
ever leaked, an attacker could just invent a new conversation_id per request
to dodge any single-user limit. The global cap bounds worst-case cost
exposure regardless of how many "users" a request claims to be.

Storage: Azure Table Storage (same account already used elsewhere), one
table, PartitionKey = today's date (UTC), RowKey = conversation_id for
per-user rows, RowKey = "__global__" for the global row. Table Storage has
no atomic increment — uses a small optimistic-retry loop, acceptable at this
volume (a handful of team members, not a high-concurrency system).
"""

import logging
import os
from datetime import datetime, timezone

from azure.core import MatchConditions
from azure.core.exceptions import ResourceExistsError
from azure.data.tables import TableClient, UpdateMode

USAGE_TABLE = "dailyusage"
GLOBAL_ROW_KEY = "__global__"

PER_USER_DAILY_LIMIT = int(os.environ.get("PER_USER_DAILY_LIMIT", "20"))
GLOBAL_DAILY_LIMIT = int(os.environ.get("GLOBAL_DAILY_LIMIT", "300"))

_STORAGE_CONN = os.environ.get("STORAGE_CONNECTION_STRING", "")


def _table_client() -> TableClient:
    table_client = TableClient.from_connection_string(_STORAGE_CONN, USAGE_TABLE)
    try:
        table_client.create_table()
    except Exception:
        pass  # already exists — fine
    return table_client


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _get_count(table_client: TableClient, partition: str, row: str) -> tuple[int, str | None]:
    """Returns (count, etag). etag is None if the row doesn't exist yet."""
    try:
        entity = table_client.get_entity(partition_key=partition, row_key=row)
        return entity.get("Count", 0), entity.metadata.get("etag")
    except Exception:
        return 0, None


def _increment(table_client: TableClient, partition: str, row: str) -> int:
    """Optimistic-concurrency increment. Returns the new count."""
    for _ in range(5):
        count, etag = _get_count(table_client, partition, row)
        entity = {"PartitionKey": partition, "RowKey": row, "Count": count + 1}
        try:
            if etag is None:
                table_client.create_entity(entity)
            else:
                table_client.update_entity(
                    entity, mode=UpdateMode.REPLACE, etag=etag,
                    match_condition=MatchConditions.IfNotModified,
                )
            return count + 1
        except ResourceExistsError:
            continue  # someone else created it first — retry, will hit the update path
        except Exception:
            continue  # etag mismatch (concurrent update) — retry with fresh count
    # Fell through all retries — fail open rather than silently blocking a real user
    logging.warning("rate_limit: increment retry limit hit for %s/%s, failing open", partition, row)
    return 0


def check_and_increment(conversation_id: str) -> tuple[bool, int, int]:
    """Call before processing a real message. Returns (allowed, user_used, user_limit).

    Increments both the per-user and global counters atomically-ish. If either
    cap is already exceeded, returns allowed=False WITHOUT incrementing
    further (so a blocked user doesn't keep burning global budget by retrying).
    """
    if not _STORAGE_CONN:
        return True, 0, PER_USER_DAILY_LIMIT  # not configured — fail open, don't block real usage

    table_client = _table_client()
    today = _today()

    user_used, _ = _get_count(table_client, today, conversation_id)
    global_used, _ = _get_count(table_client, today, GLOBAL_ROW_KEY)

    if user_used >= PER_USER_DAILY_LIMIT or global_used >= GLOBAL_DAILY_LIMIT:
        return False, user_used, PER_USER_DAILY_LIMIT

    user_used = _increment(table_client, today, conversation_id)
    _increment(table_client, today, GLOBAL_ROW_KEY)
    return True, user_used, PER_USER_DAILY_LIMIT


def get_usage(conversation_id: str) -> tuple[int, int]:
    """Read-only — for staff asking 'how many messages do I have left'."""
    if not _STORAGE_CONN:
        return 0, PER_USER_DAILY_LIMIT
    table_client = _table_client()
    used, _ = _get_count(table_client, _today(), conversation_id)
    return used, PER_USER_DAILY_LIMIT
