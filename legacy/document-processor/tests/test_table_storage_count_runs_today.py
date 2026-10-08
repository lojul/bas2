"""count_runs_today() backs the daily Slack digest (function_app.py's
daily_processing_summary) — must only count today's rows and tolerate an
unset AZURE_TABLE_SAS without crashing."""

from datetime import datetime, timedelta, timezone

from src.utils import table_storage


class _FakeEntities(list):
    pass


class _FakeTableClient:
    def __init__(self, rows):
        self._rows = rows

    def query_entities(self, filter_str):
        return _FakeEntities(self._rows)


def test_count_runs_today_counts_only_todays_rows(monkeypatch):
    now = datetime.now(timezone.utc)
    today_stamp = now.strftime("%Y%m%dT%H%M%S")
    yesterday_stamp = (now - timedelta(days=1)).strftime("%Y%m%dT%H%M%S")

    rows = [
        {"RowKey": f"{today_stamp}_aaa", "status": "success", "source": "assistant"},
        {"RowKey": f"{today_stamp}_bbb", "status": "success", "source": "onedrive"},
        {"RowKey": f"{today_stamp}_ccc", "status": "error", "source": ""},  # legacy row, no source
        {"RowKey": f"{yesterday_stamp}_ddd", "status": "success", "source": "assistant"},  # excluded
    ]
    monkeypatch.setattr(table_storage, "_client", lambda: _FakeTableClient(rows))

    counts = table_storage.count_runs_today()
    assert counts == {
        "success": 2, "error": 1, "unsupported": 0,
        "manual_success": 1, "manual_error": 1,
        "onedrive_success": 1, "onedrive_error": 0,
    }


def test_count_runs_today_fails_open_without_table_sas(monkeypatch):
    monkeypatch.setattr(table_storage, "_client", lambda: None)
    assert table_storage.count_runs_today() == {
        "success": 0, "error": 0, "unsupported": 0,
        "manual_success": 0, "manual_error": 0,
        "onedrive_success": 0, "onedrive_error": 0,
    }
