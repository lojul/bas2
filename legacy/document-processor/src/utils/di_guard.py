"""Daily cost guard for Azure Document Intelligence.

Circuit breaker for the known-dangerous component: a runaway loop once burned
$4,012 of DI in two days. Azure budget alerts lag 8-24h and only email — this
counts pages in real time and hard-stops OCR past the daily ceiling.

Counter lives in Azure Table Storage (shared by App Service + Function App).
If Table Storage is unavailable the guard fails OPEN (processing continues) —
availability of the product wins over strictness of the guard.
"""

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_ACCOUNT = "blobhk04472"
_TABLE = "DiUsage"
_DEFAULT_DAILY_PAGE_LIMIT = 200


class DailyLimitExceeded(Exception):
    """Raised when today's DI page budget is exhausted."""


def _limit() -> int:
    try:
        return int(os.environ.get("DI_DAILY_PAGE_LIMIT", _DEFAULT_DAILY_PAGE_LIMIT))
    except ValueError:
        return _DEFAULT_DAILY_PAGE_LIMIT


def _table_client():
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


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_usage_today() -> int:
    """Pages OCR'd today (UTC). 0 if unavailable."""
    try:
        client = _table_client()
        if client is None:
            return 0
        entity = client.get_entity(partition_key="di", row_key=_today_key())
        return int(entity.get("pages", 0))
    except Exception:
        return 0


def check_di_budget(pages_about_to_process: int = 1) -> None:
    """Raise DailyLimitExceeded if the daily page ceiling is already reached.

    Call BEFORE the DI request. Fails open on storage errors.
    """
    limit = _limit()
    used = get_usage_today()
    if used >= limit:
        _alert_admin(used, limit)
        raise DailyLimitExceeded(
            f"已達每日 OCR 上限（{limit} 頁，今日已用 {used} 頁），文件處理暫停至明天"
        )


def record_di_usage(pages: int) -> None:
    """Add pages to today's counter. Call AFTER a successful DI request."""
    if pages <= 0:
        pages = 1
    total = pages
    try:
        client = _table_client()
        if client is None:
            return
        key = _today_key()
        try:
            entity = client.get_entity(partition_key="di", row_key=key)
            total = int(entity.get("pages", 0)) + pages
            entity["pages"] = total
            client.update_entity(entity)
        except Exception:
            client.upsert_entity({"PartitionKey": "di", "RowKey": key, "pages": pages})
    except Exception as e:
        logger.warning("di_guard: failed to record usage: %s", e)
        return

    limit = _limit()
    if total >= limit:
        _alert_admin(total, limit)


_alerted_today: set[str] = set()


def _alert_admin(used: int, limit: int) -> None:
    """WhatsApp the admin once per day per process when the ceiling trips."""
    key = _today_key()
    if key in _alerted_today:
        return
    _alerted_today.add(key)

    admin = os.environ.get("ADMIN_WHATSAPP", "")
    logger.error("DI daily limit reached: %s/%s pages", used, limit)
    if not admin:
        return
    try:
        from src.utils.whatsapp_notify import send_whatsapp
        send_whatsapp(
            admin,
            f"⚠️ OCR 已達每日上限（{limit} 頁），文件處理已暫停至明天（UTC 午夜重置）。\n"
            f"今日用量：{used} 頁。\n"
            f"如需調高上限，請更新 DI_DAILY_PAGE_LIMIT 設定。",
        )
    except Exception as e:
        logger.warning("di_guard: admin alert failed: %s", e)
