"""Guards against the empty-delta-link failure mode: an empty token read back
from storage looks like "no baseline" and would send the OneDrive timer down
the full-traversal path (re-OCRs the whole watched folder). See
src/utils/onedrive_delta_store.py and function_app.py's onedrive_sync."""

import pytest

from src.utils import onedrive_delta_store as store


class _FakeTableClient:
    def __init__(self):
        self.entities = {}

    def get_entity(self, partition_key, row_key):
        key = (partition_key, row_key)
        if key not in self.entities:
            raise Exception("not found")
        return self.entities[key]

    def upsert_entity(self, entity):
        key = (entity["PartitionKey"], entity["RowKey"])
        self.entities[key] = entity

    def delete_entity(self, partition_key, row_key):
        self.entities.pop((partition_key, row_key), None)


def test_save_delta_link_refuses_empty(monkeypatch):
    with pytest.raises(ValueError):
        store.save_delta_link("")
    with pytest.raises(ValueError):
        store.save_delta_link("   ")


def test_load_delta_link_returns_none_when_missing(monkeypatch):
    monkeypatch.setattr(store, "_client", lambda: _FakeTableClient())
    assert store.load_delta_link() is None


def test_save_then_load_round_trip(monkeypatch):
    fake = _FakeTableClient()
    monkeypatch.setattr(store, "_client", lambda: fake)

    store.save_delta_link("https://graph.microsoft.com/delta?token=abc123")
    assert store.load_delta_link() == "https://graph.microsoft.com/delta?token=abc123"


def test_delete_delta_link_clears_state(monkeypatch):
    fake = _FakeTableClient()
    monkeypatch.setattr(store, "_client", lambda: fake)

    store.save_delta_link("https://graph.microsoft.com/delta?token=abc123")
    store.delete_delta_link()
    assert store.load_delta_link() is None


def test_load_delta_link_fails_open_without_table_sas(monkeypatch):
    monkeypatch.setattr(store, "_client", lambda: None)
    assert store.load_delta_link() is None
