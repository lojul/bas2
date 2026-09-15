"""Delta-sync safety behavior: hard-stop on 410/missing-deltaLink (never fall
back to a full traversal silently), and the since-filter that bounds a
legitimate delta response. See CLAUDE.md's OneDrive-sync safeguards
discussion and src/utils/graph_client.py."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from src.utils.graph_client import (
    DeltaLinkExpiredError,
    GraphClient,
    MissingDeltaLinkError,
)


@pytest.fixture
def client(monkeypatch):
    gc = GraphClient.__new__(GraphClient)  # skip __init__ (no real MSAL token)
    monkeypatch.setattr(gc, "_get_token", lambda: "fake-token")
    return gc


def _item(name: str, modified: str, item_id: str = "1") -> dict:
    return {
        "id": item_id,
        "name": name,
        "file": {},
        "lastModifiedDateTime": modified,
        "parentReference": {"path": "/drives/x/root:/In"},
    }


def test_iter_delta_changes_raises_on_410(client, monkeypatch):
    def fake_get(url):
        request = httpx.Request("GET", url)
        response = httpx.Response(410, request=request)
        raise httpx.HTTPStatusError("410 Gone", request=request, response=response)

    monkeypatch.setattr(client, "get", fake_get)

    with pytest.raises(DeltaLinkExpiredError):
        client.iter_delta_changes("drive1", "item1", delta_link="https://stale-link")


def test_iter_delta_changes_raises_on_missing_delta_link(client, monkeypatch):
    monkeypatch.setattr(client, "get", lambda url: {"value": []})  # no @odata.deltaLink

    with pytest.raises(MissingDeltaLinkError):
        client.iter_delta_changes("drive1", "item1", delta_link=None)


def test_iter_delta_changes_filters_by_since(client, monkeypatch):
    now = datetime.now(timezone.utc)
    old_item = _item("old.pdf", (now - timedelta(days=200)).isoformat().replace("+00:00", "Z"))
    new_item = _item("new.pdf", now.isoformat().replace("+00:00", "Z"), item_id="2")

    monkeypatch.setattr(
        client, "get",
        lambda url: {"value": [old_item, new_item], "@odata.deltaLink": "https://next-link"},
    )

    items, delta_link = client.iter_delta_changes(
        "drive1", "item1", delta_link=None, since=now - timedelta(days=90),
    )

    assert [i["name"] for i in items] == ["new.pdf"]
    assert delta_link == "https://next-link"


def test_iter_delta_changes_skips_folders(client, monkeypatch):
    folder = {"id": "f1", "name": "Subfolder", "folder": {}, "lastModifiedDateTime": "2026-01-01T00:00:00Z"}
    file_item = _item("doc.pdf", "2026-01-01T00:00:00Z")

    monkeypatch.setattr(
        client, "get",
        lambda url: {"value": [folder, file_item], "@odata.deltaLink": "https://next-link"},
    )

    items, _ = client.iter_delta_changes("drive1", "item1", delta_link=None)
    assert [i["name"] for i in items] == ["doc.pdf"]


def test_iter_delta_changes_uses_existing_delta_link_verbatim(client, monkeypatch):
    seen_urls = []

    def fake_get(url):
        seen_urls.append(url)
        return {"value": [], "@odata.deltaLink": "https://next-link"}

    monkeypatch.setattr(client, "get", fake_get)
    client.iter_delta_changes("drive1", "item1", delta_link="https://saved-delta-link")

    assert seen_urls == ["https://saved-delta-link"]
