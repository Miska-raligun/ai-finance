"""收据图片归档：落盘 / dedup / 列表 / 删除。"""
import hashlib

import pytest


def test_store_receipt_writes_file_and_row(auth_client, app, tmp_path):
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    img = b"\x89PNG\r\n\x1a\n\x00\x01\x02\x03"  # 占位字节流，store 不解析图像

    with app.app_context():
        from services.receipts import store_receipt
        r = store_receipt(uid, img, "image/png")
        assert r["sha256"] == hashlib.sha256(img).hexdigest()
        assert r["deduped"] is False
        assert r["path"].endswith(".png")
        # 再调一次 → dedup
        r2 = store_receipt(uid, img, "image/png")
        assert r2["deduped"] is True
        assert r2["id"] == r["id"]


def test_store_receipt_rejects_unknown_mime(auth_client, app):
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    with app.app_context():
        from services.receipts import store_receipt
        with pytest.raises(ValueError):
            store_receipt(uid, b"x", "image/gif")
        with pytest.raises(ValueError):
            store_receipt(uid, b"", "image/png")


def test_list_endpoint_returns_user_only(auth_client, app):
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    with app.app_context():
        from services.receipts import store_receipt
        store_receipt(uid, b"img-bytes-A", "image/jpeg")
        store_receipt(uid, b"img-bytes-B", "image/jpeg")

    r = auth_client.get("/api/receipts")
    assert r.status_code == 200
    rows = r.get_json()
    assert len(rows) == 2
    assert all("sha256" in row for row in rows)


def test_get_image_404_on_missing(auth_client):
    r = auth_client.get("/api/receipts/99999")
    assert r.status_code == 404


def test_attach_to_record(auth_client, app):
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    with app.app_context():
        from services.receipts import store_receipt, attach_to_record, get_receipt
        r = store_receipt(uid, b"img-bytes-C", "image/jpeg")
        ok = attach_to_record(uid, r["id"], record_id=42, kind="expense")
        assert ok
        info = get_receipt(uid, r["id"])
        assert info["record_id"] == 42
        assert info["record_kind"] == "expense"
        # 已关联的不允许再次 attach
        ok2 = attach_to_record(uid, r["id"], record_id=99, kind="expense")
        assert not ok2


def test_delete_purges_orphan_file(auth_client, app):
    import os
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    with app.app_context():
        from services.receipts import store_receipt, absolute_path
        r = store_receipt(uid, b"img-bytes-D", "image/jpeg")
        assert os.path.isfile(absolute_path(r["path"]))

    res = auth_client.delete(f"/api/receipts/{r['id']}")
    assert res.status_code == 200

    with app.app_context():
        from services.receipts import absolute_path
        # 同 sha 已无引用，物理文件应被删除
        assert not os.path.isfile(absolute_path(r["path"]))
