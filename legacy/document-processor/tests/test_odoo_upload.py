"""Tests for the Odoo 文件上傳 channel (src/utils/odoo_upload.py + api/routes/odoo_upload.py)."""

import base64
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.state import DocumentType
from src.utils import odoo_upload as ou

STATUS_SEL = {"type": "selection", "selection": [
    ("pending", "待處理"), ("processing", "處理中"), ("done", "完成"), ("error", "失敗"),
]}
TYPE_SEL = {"type": "selection", "selection": [
    ("auto", "自動"), ("listing", "放盤"), ("listing_list", "放盤表"),
    ("pitching_deck", "樓書"), ("news", "新聞"), ("contact", "名片"),
]}


class FakeOdoo:
    """Minimal execute_kw stand-in for the upload model."""

    def __init__(self, fields: dict, record: dict):
        self.fields = fields
        self.record = record
        self.writes: list[dict] = []
        self.posts: list[dict] = []

    def execute_kw(self, db, uid, key, model, method, args, kwargs=None):
        if method == "fields_get":
            return self.fields
        if method == "read" and model == ou.UPLOAD_MODEL:
            return [self.record] if self.record else []
        if method == "read" and model == "res.users":
            return [{"partner_id": [7, "Staff"]}]
        if method == "write":
            self.writes.append(args[1])
            return True
        if method == "message_post":
            self.posts.append(kwargs)
            return 1
        raise AssertionError(f"unexpected call {model}.{method}")


@pytest.fixture
def odoo():
    fake = FakeOdoo(
        fields={ou.F_FILE: {"type": "binary"}, ou.F_FILENAME: {"type": "char"},
                ou.F_DOC_TYPE: TYPE_SEL, ou.F_ALLOW_DUP: {"type": "boolean"},
                ou.F_STATUS: STATUS_SEL, ou.F_RESULT: {"type": "text"},
                ou.F_LISTINGS: {"type": "many2many"}},
        record={ou.F_FILE: base64.b64encode(b"%PDF-1.4 x").decode(), ou.F_FILENAME: "灣仔道188號.pdf",
                ou.F_DOC_TYPE: "listing_list", ou.F_ALLOW_DUP: False,
                "display_name": "Upload 1", "create_uid": [2, "Staff"]},
    )
    with patch.object(ou, "_connect", return_value=(fake, 1, "k")):
        yield fake


@pytest.mark.parametrize("value,expected", [
    (False, None), ("auto", None), ("listing", "listing"), ("listing_list", "listing_list"),
    ("pitching_deck", "pitching_deck"), ("news", "news"), ("contact", "contact"),
])
def test_map_doc_type_selection(value, expected):
    assert ou.map_doc_type(value, TYPE_SEL) == expected


def test_map_doc_type_studio_generated_keys():
    # Studio may generate opaque keys; the label decides
    sel = {"selection": [("x1", "放盤表"), ("x2", "放盤"), ("x3", "自動")]}
    assert ou.map_doc_type("x1", sel) == "listing_list"
    assert ou.map_doc_type("x2", sel) == "listing"
    assert ou.map_doc_type("x3", sel) is None


def test_status_value_by_label_key_or_text():
    assert ou.status_value(ou.STATUS_DONE, STATUS_SEL) == "done"
    assert ou.status_value(ou.STATUS_DONE, {"selection": [("x9", "完成")]}) == "x9"
    assert ou.status_value(ou.STATUS_DONE, {"type": "char"}) == "完成"


def test_fetch_upload(odoo):
    up = ou.fetch_upload(5)
    assert up == {"file_bytes": b"%PDF-1.4 x", "file_name": "灣仔道188號.pdf",
                  "doc_type": "listing_list", "allow_duplicate": False, "has_name": False}


def test_fetch_upload_no_file(odoo):
    odoo.record[ou.F_FILE] = False
    with pytest.raises(ou.OdooUploadError):
        ou.fetch_upload(5)


def test_fetch_upload_guesses_name_and_skips_missing_fields(odoo):
    odoo.fields = {ou.F_FILE: {"type": "binary"}}
    odoo.record = {ou.F_FILE: base64.b64encode(b"\x89PNG\r\n\x1a\nxx").decode(), "display_name": "Upload 1"}
    up = ou.fetch_upload(5)
    assert up["file_name"] == "Upload 1.png" and up["doc_type"] is None


def _final(doc_type="listing_list", sync="synced", ids="146,147"):
    f = MagicMock()
    f.document_type = DocumentType(doc_type)
    f.odoo_sync_status = sync
    f.odoo_record_id = ids
    return f


def test_report_result_success_links_listings(odoo):
    assert ou.report_result("5", "✅ 處理完成：a.pdf\n分類：x", _final()) is True
    assert odoo.writes == [{ou.F_STATUS: "done", ou.F_RESULT: "✅ 處理完成：a.pdf\n分類：x",
                            ou.F_LISTINGS: [(6, 0, [146, 147])]}]
    assert odoo.posts[0]["body"] == "✅ 處理完成：a.pdf" and odoo.posts[0]["partner_ids"] == [7]


def test_report_result_contact_does_not_link_listings(odoo):
    ou.report_result("5", "✅ 處理完成", _final("contact", ids="99"))
    assert ou.F_LISTINGS not in odoo.writes[0]


def test_report_result_failure(odoo):
    ou.report_result("5", "❌ 處理失敗：a.pdf", None)
    assert odoo.writes[0][ou.F_STATUS] == "error"


def test_report_result_odoo_sync_error(odoo):
    ou.report_result("5", "✅ 處理完成\n⚠️ Odoo 同步失敗", _final(sync="error"))
    assert odoo.writes[0][ou.F_STATUS] == "error"


def test_report_result_bad_target():
    assert ou.report_result("abc", "✅", None) is False


def test_channel_notify_routes_odoo():
    from src.utils.channel_notify import notify
    with patch("src.utils.odoo_upload.report_result", return_value=True) as rr:
        assert notify("odoo", "5", "msg", "FINAL") is True
    rr.assert_called_once_with("5", "msg", "FINAL")


# ── Route ────────────────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    from api.routes.odoo_upload import router
    monkeypatch.setenv("ODOO_UPLOAD_WEBHOOK_TOKEN", "secret")
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_route_rejects_bad_token(client):
    assert client.post("/api/odoo/upload?token=nope", json={"_id": 5}).status_code == 401
    assert client.post("/api/odoo/upload", json={"_id": 5}).status_code == 401


def test_route_fails_closed_without_token(client, monkeypatch):
    monkeypatch.setenv("ODOO_UPLOAD_WEBHOOK_TOKEN", "")
    assert client.post("/api/odoo/upload?token=", json={"_id": 5}).status_code == 401


def test_route_rejects_other_model(client):
    r = client.post("/api/odoo/upload?token=secret", json={"_id": 5, "_model": "res.partner"})
    assert r.status_code == 400


def test_route_queues_job(client, odoo):
    with patch("src.utils.job_queue.enqueue_pipeline_job", return_value=True) as enq:
        r = client.post("/api/odoo/upload?token=secret", json={"_id": 5, "_model": ou.UPLOAD_MODEL})
    assert r.status_code == 200 and r.json()["status"] == "queued"
    args, kwargs = enq.call_args
    assert args == (b"%PDF-1.4 x", "灣仔道188號.pdf")
    assert kwargs["forced_type"] == DocumentType.LISTING_LIST
    assert kwargs["notify_channel"] == "odoo" and kwargs["notify_user"] == "5"
    assert kwargs["source"] == "odoo" and kwargs["skip_duplicate_check"] is False
    assert odoo.writes[0][ou.F_STATUS] == "processing"
    assert odoo.writes[0]["x_name"] == "灣仔道188號.pdf"


def test_route_queue_down_marks_error(client, odoo):
    with patch("src.utils.job_queue.enqueue_pipeline_job", return_value=False):
        r = client.post("/api/odoo/upload?token=secret", json={"_id": 5})
    assert r.status_code == 503
    assert odoo.writes[-1][ou.F_STATUS] == "error"


def test_route_no_file_marks_error(client, odoo):
    odoo.record[ou.F_FILE] = False
    r = client.post("/api/odoo/upload?token=secret", json={"_id": 5})
    assert r.json()["status"] == "error"
    assert odoo.writes[-1][ou.F_STATUS] == "error"
