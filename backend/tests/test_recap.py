"""本月回顾 /api/reports/recap：亮点聚合 + 文案 fallback / LLM。"""
from datetime import datetime


def _seed(app, uid):
    from db import get_db
    period = datetime.now().strftime("%Y-%m")
    with app.app_context():
        db = get_db()
        for day, cat, amt in [(2, "餐饮", 60), (2, "餐饮", 40), (3, "交通", 30),
                              (10, "购物", 800), (11, "餐饮", 50)]:
            db.execute(
                "INSERT INTO records (user_id, category, amount, note, date) "
                "VALUES (?, ?, ?, '', ?)",
                (uid, cat, amt, f"{period}-{day:02d}"),
            )
        db.execute(
            "INSERT INTO income (user_id, category, amount, note, date) "
            "VALUES (?, '工资', 5000, '', ?)",
            (uid, f"{period}-05"),
        )
        db.commit()
    return period


def test_recap_requires_login(client):
    r = client.get("/api/reports/recap")
    assert r.status_code == 401


def test_recap_fallback_without_llm(auth_client, app, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    period = _seed(app, uid)

    r = auth_client.get(f"/api/reports/recap?month={period}")
    assert r.status_code == 200
    body = r.get_json()
    assert body["source"] == "fallback"
    assert body["spend_total"] == 980.0
    assert body["income_total"] == 5000.0
    assert body["largest_txn"]["amount"] == 800.0
    assert body["largest_txn"]["category"] == "购物"
    assert body["highest_day"]["total"] == 800.0
    assert body["top_category"]["category"] == "购物"
    assert body["caption"]


def test_recap_uses_llm_caption(auth_client, app, monkeypatch):
    from services.llm_config import save_llm_config
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    period = _seed(app, uid)
    with app.app_context():
        save_llm_config(uid, url="https://x", apikey="sk-test", model="m", persona="")

    fake = {"choices": [{"message": {"content": "这个月买买买有点上头哦 🛍️"}}],
            "usage": {"total_tokens": 8}}
    monkeypatch.setattr("services.recap._call_llm", lambda **kw: fake)

    r = auth_client.get(f"/api/reports/recap?month={period}")
    assert r.status_code == 200
    body = r.get_json()
    assert body["source"] == "llm"
    assert "上头" in body["caption"]


def test_recap_empty_month(auth_client, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    r = auth_client.get("/api/reports/recap?month=2099-01")
    assert r.status_code == 200
    body = r.get_json()
    assert body["source"] == "empty"
    assert body["spend_total"] == 0
