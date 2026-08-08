"""财务体检 /api/checkup：评分 fallback / LLM / 存档 + 历史趋势。"""
from datetime import datetime


def _seed(app, uid):
    from db import get_db
    period = datetime.now().strftime("%Y-%m")
    with app.app_context():
        db = get_db()
        for day, cat, amt in [(2, "餐饮", 600), (10, "购物", 1200), (15, "交通", 200)]:
            db.execute(
                "INSERT INTO records (user_id, category, amount, note, date) "
                "VALUES (?, ?, ?, '', ?)",
                (uid, cat, amt, f"{period}-{day:02d}"),
            )
        db.execute(
            "INSERT INTO income (user_id, category, amount, note, date) "
            "VALUES (?, '工资', 8000, '', ?)",
            (uid, f"{period}-05"),
        )
        db.commit()
    return period


def test_checkup_requires_login(client):
    assert client.post("/api/checkup/compute").status_code == 401
    assert client.get("/api/checkup/history").status_code == 401


def test_checkup_fallback_without_llm(auth_client, app, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    period = _seed(app, uid)

    r = auth_client.post(f"/api/checkup/compute?month={period}")
    assert r.status_code == 200
    body = r.get_json()
    assert body["source"] == "fallback"
    assert 0 <= body["score"] <= 100
    assert len(body["dimensions"]) == 4
    assert body["grade"]

    # 已存档：current 能取回，history 出现一个点
    cur = auth_client.get(f"/api/checkup/current?month={period}").get_json()
    assert cur["score"] == body["score"]
    hist = auth_client.get("/api/checkup/history").get_json()
    assert any(h["period"] == period for h in hist)


def test_checkup_uses_llm_score(auth_client, app, monkeypatch):
    from services.llm_config import save_llm_config
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    period = _seed(app, uid)
    with app.app_context():
        save_llm_config(uid, url="https://x", apikey="sk-test", model="m", persona="")

    content = (
        '{"score": 78, "dimensions": ['
        '{"name":"储蓄率","score":22,"max":25,"comment":"不错"},'
        '{"name":"预算执行","score":18,"max":25,"comment":"还行"},'
        '{"name":"应急储备","score":20,"max":25,"comment":"充足"},'
        '{"name":"消费结构","score":18,"max":25,"comment":"略集中"}],'
        '"summary":"整体健康", "report":"继续保持"}'
    )
    fake = {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 20}}
    monkeypatch.setattr("services.checkup._call_llm", lambda **kw: fake)

    body = auth_client.post(f"/api/checkup/compute?month={period}").get_json()
    assert body["source"] == "llm"
    assert body["score"] == 78
    assert body["grade"] == "良好"
    assert len(body["dimensions"]) == 4


def test_checkup_fallback_on_bad_json(auth_client, app, monkeypatch):
    from services.llm_config import save_llm_config
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    period = _seed(app, uid)
    with app.app_context():
        save_llm_config(uid, url="https://x", apikey="sk-test", model="m", persona="")

    bad = {"choices": [{"message": {"content": "你的财务挺健康的~"}}], "usage": {"total_tokens": 5}}
    monkeypatch.setattr("services.checkup._call_llm", lambda **kw: bad)

    body = auth_client.post(f"/api/checkup/compute?month={period}").get_json()
    assert body["source"] == "fallback"
    assert 0 <= body["score"] <= 100


def test_checkup_empty_month(auth_client, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    body = auth_client.post("/api/checkup/compute?month=2099-02").get_json()
    assert body["source"] == "empty"
    assert body["score"] == 0
    # 空月不应写入历史
    hist = auth_client.get("/api/checkup/history").get_json()
    assert all(h["period"] != "2099-02" for h in hist)
