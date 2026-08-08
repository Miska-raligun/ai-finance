"""导出端点 /api/export?format=csv|json|xlsx 三种格式。

旧 /api/export/csv 兼容路径仍可用；新 /api/export 统一入口走 _do_export。
"""
import json as _json


def _seed_record(app, uid, *, category="餐饮", amount=12.5, date="2025-04-01"):
    from db import get_db
    with app.app_context():
        get_db().execute(
            "INSERT INTO records (user_id, category, amount, note, date) "
            "VALUES (?, ?, ?, '午餐', ?)",
            (uid, category, amount, date),
        )
        get_db().commit()


def test_csv_endpoint_back_compat(auth_client, app):
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    _seed_record(app, uid)
    r = auth_client.get("/api/export/csv?type=records")
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    body = r.get_data(as_text=True)
    assert "日期,分类,金额,备注" in body
    assert "餐饮" in body


def test_unified_export_csv(auth_client, app):
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    _seed_record(app, uid)
    r = auth_client.get("/api/export?type=records&format=csv")
    assert r.status_code == 200
    assert r.mimetype == "text/csv"


def test_unified_export_json(auth_client, app):
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    _seed_record(app, uid, category="工资", amount=10000, date="2025-04-10")
    _seed_record(app, uid, category="餐饮", amount=12.5)
    r = auth_client.get("/api/export?type=records&format=json")
    assert r.status_code == 200
    assert r.mimetype == "application/json"
    body = _json.loads(r.get_data(as_text=True))
    assert body["type"] == "records"
    assert body["count"] == 2
    assert "日期" in body["fields"]
    cats = {row["category"] for row in body["rows"]}
    assert "餐饮" in cats and "工资" in cats


def test_unified_export_xlsx(auth_client, app):
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    _seed_record(app, uid)
    r = auth_client.get("/api/export?type=records&format=xlsx")
    # openpyxl 未装时端点应 501；装了应 200 + xlsx mimetype
    if r.status_code == 501:
        return
    assert r.status_code == 200
    assert "spreadsheetml" in r.mimetype
    # 文件头应是 PK（zip）— xlsx 是 zip 容器
    data = r.get_data()
    assert data[:2] == b"PK"


def test_unsupported_format_400(auth_client):
    r = auth_client.get("/api/export?type=records&format=pdf")
    assert r.status_code == 400


def test_unsupported_kind_400(auth_client):
    r = auth_client.get("/api/export?type=garbage&format=csv")
    assert r.status_code == 400
