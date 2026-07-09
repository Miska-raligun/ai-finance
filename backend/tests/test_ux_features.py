"""本轮体验功能的回归测试:首页速览 / 软删撤销 / 关键词搜索 / recap 缓存失效。"""
from __future__ import annotations

from datetime import datetime

import pytest


def _add_record(client, category, amount, note="", date=None):
    r = client.post("/api/records", json={
        "category": category, "amount": amount, "note": note,
        "date": date or datetime.now().strftime("%Y-%m-%d"),
    })
    assert r.status_code == 200, r.get_data(as_text=True)


# ── /api/stats/today ─────────────────────────────────────────────

def test_stats_today_reflects_records_and_budget(app, auth_client):
    today = datetime.now().strftime("%Y-%m-%d")
    month = today[:7]
    _add_record(auth_client, "餐饮", 30, date=today)
    _add_record(auth_client, "交通", 20, date=f"{month}-01")

    r = auth_client.get("/api/stats/today")
    assert r.status_code == 200
    data = r.get_json()
    assert data["today_spend"] >= 30
    assert data["month_spend"] >= 50
    # 没设预算时 budget_remaining 为 null
    assert data["budget_remaining"] is None

    auth_client.post("/api/budgets", json={"category": "餐饮", "amount": 500, "month": month})
    data2 = auth_client.get("/api/stats/today").get_json()
    assert data2["budget_total"] == 500
    assert data2["budget_remaining"] == pytest.approx(500 - data2["month_spend"])


# ── 软删除 + 撤销 ────────────────────────────────────────────────

def test_delete_then_restore_roundtrip(app, auth_client):
    _add_record(auth_client, "餐饮", 66, note="火锅")
    rows = auth_client.get("/api/records").get_json()["data"]
    rid = rows[0]["id"]

    r = auth_client.delete(f"/api/records/{rid}")
    assert r.get_json() == {"success": True, "undoable": True}
    # 删除后列表里立刻看不到
    ids = [x["id"] for x in auth_client.get("/api/records").get_json()["data"]]
    assert rid not in ids

    r = auth_client.post(f"/api/records/{rid}/restore")
    assert r.get_json()["success"] is True
    ids = [x["id"] for x in auth_client.get("/api/records").get_json()["data"]]
    assert rid in ids

    # 已恢复的行再 restore 一次应 404
    assert auth_client.post(f"/api/records/{rid}/restore").status_code == 404


def test_soft_deleted_rows_excluded_from_stats(app, auth_client):
    today = datetime.now().strftime("%Y-%m-%d")
    _add_record(auth_client, "购物", 100, date=today)
    before = auth_client.get("/api/stats/today").get_json()["today_spend"]

    rid = auth_client.get("/api/records").get_json()["data"][0]["id"]
    auth_client.delete(f"/api/records/{rid}")
    after = auth_client.get("/api/stats/today").get_json()["today_spend"]
    assert after == pytest.approx(before - 100)


# ── 关键词搜索 ───────────────────────────────────────────────────

def test_records_keyword_search(app, auth_client):
    _add_record(auth_client, "餐饮", 88, note="和小王吃火锅")
    _add_record(auth_client, "交通", 12, note="地铁")

    hits = auth_client.get("/api/records", query_string={"q": "火锅"}).get_json()
    assert hits["total"] == 1
    assert hits["data"][0]["note"] == "和小王吃火锅"

    # 分类名也能匹配
    hits = auth_client.get("/api/records", query_string={"q": "交通"}).get_json()
    assert hits["total"] == 1

    # LIKE 通配符注入:% 应被当成字面量,匹配不到任何行
    hits = auth_client.get("/api/records", query_string={"q": "%"}).get_json()
    assert hits["total"] == 0


# ── recap 缓存失效 ───────────────────────────────────────────────

def test_recap_cache_invalidated_on_write(app, auth_client):
    """记新账后 recap_cache 里的旧行应被清掉(invalidate_user 连带失效)。"""
    from db import get_db
    with app.app_context():
        db = get_db()
        uid = db.execute("SELECT id FROM users WHERE username='tester'").fetchone()[0]
        db.execute(
            "INSERT INTO recap_cache (user_id, period, highlights_json, created_at) "
            "VALUES (?, ?, ?, ?)",
            (uid, "2026-07", '{"stale": true}', "2026-07-01T00:00:00"),
        )
        db.commit()

    _add_record(auth_client, "餐饮", 10)

    with app.app_context():
        row = get_db().execute(
            "SELECT 1 FROM recap_cache WHERE user_id = ?", (uid,)
        ).fetchone()
        assert row is None
