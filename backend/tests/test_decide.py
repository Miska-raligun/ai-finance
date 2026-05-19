"""购前决策助手 /api/decide：参数校验 + LLM fallback。"""


def test_decide_requires_login(client):
    r = client.post("/api/decide", json={"item": "键盘", "price": 1200})
    assert r.status_code == 401


def test_decide_rejects_missing_fields(auth_client):
    r = auth_client.post("/api/decide", json={"item": ""})
    assert r.status_code == 400
    r = auth_client.post("/api/decide", json={"item": "键盘", "price": 0})
    assert r.status_code == 400


def test_decide_rejects_extreme_price(auth_client):
    r = auth_client.post("/api/decide", json={"item": "私人飞机", "price": 99_999_999})
    assert r.status_code == 400


def test_decide_falls_back_without_llm(auth_client, app):
    """没配 LLM key 时，返回本地规则建议，且含 impact 估算。"""
    from datetime import datetime, timedelta
    from db import get_db
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    today = datetime.now().date()
    # 喂近 60 天的消费数据让 impact 计算有意义
    with app.app_context():
        db = get_db()
        for days_ago, amt in [(7, 800), (15, 1200), (25, 900),
                              (40, 1100), (50, 700), (58, 1000)]:
            d = (today - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            db.execute(
                "INSERT INTO records (user_id, category, amount, note, date) "
                "VALUES (?, '餐饮', ?, '', ?)",
                (uid, amt, d),
            )
        db.commit()

    r = auth_client.post("/api/decide", json={"item": "机械键盘", "price": 1200})
    assert r.status_code == 200
    body = r.get_json()
    assert body["source"] == "fallback"
    assert body["verdict"]
    assert body["impact"]["price"] == 1200.0
    # 至少有 spend_avg_monthly 算出来一个百分比
    assert body["impact"]["as_pct_of_avg_monthly_spend"] is not None


def test_decide_uses_llm_when_configured(auth_client, app, monkeypatch):
    """配了 LLM key 时调用 _call_llm 并解析返回的 JSON。"""
    from services.llm_config import save_llm_config
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    with app.app_context():
        save_llm_config(uid, url="https://x", apikey="sk-test", model="m", persona="")

    fake_response = {
        "choices": [{
            "message": {
                "content": (
                    '{"verdict":"建议等等",'
                    '"reason":"本月预算偏紧","alternatives":["二手键盘"],"tips":["等 618"]}'
                )
            }
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    monkeypatch.setattr("routes.decide._call_llm", lambda **kw: fake_response)

    r = auth_client.post("/api/decide", json={"item": "键盘", "price": 1500})
    assert r.status_code == 200
    body = r.get_json()
    assert body["source"] == "llm"
    assert body["verdict"] == "建议等等"
    assert "本月预算偏紧" in body["reason"]
    assert "二手键盘" in body["alternatives"]
    assert "等 618" in body["tips"]


def test_decide_uses_system_default_key(auth_client, monkeypatch):
    """用户没配 LLM 但系统有 DEEPSEEK_API_KEY 时，应该尝试调 LLM 而不是直接 fallback。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-system-default")

    called = {"ok": False}

    def _fake_call(**kw):
        called["ok"] = True
        return {
            "choices": [{
                "message": {
                    "content": '{"verdict":"建议买","reason":"系统默认 LLM 走通了","alternatives":[],"tips":[]}'
                }
            }],
            "usage": {"total_tokens": 10},
        }
    monkeypatch.setattr("routes.decide._call_llm", _fake_call)

    r = auth_client.post("/api/decide", json={"item": "鼠标", "price": 200})
    assert r.status_code == 200
    body = r.get_json()
    assert called["ok"] is True
    assert body["source"] == "llm"
    assert body["verdict"] == "建议买"


def test_decide_falls_back_on_invalid_llm_json(auth_client, app, monkeypatch):
    """LLM 返回非 JSON 时回退本地，不应 500。"""
    from services.llm_config import save_llm_config
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    with app.app_context():
        save_llm_config(uid, url="https://x", apikey="sk-test", model="m", persona="")

    bad = {"choices": [{"message": {"content": "我觉得这个键盘不错~"}}],
           "usage": {"total_tokens": 5}}
    monkeypatch.setattr("routes.decide._call_llm", lambda **kw: bad)

    r = auth_client.post("/api/decide", json={"item": "键盘", "price": 800})
    assert r.status_code == 200
    body = r.get_json()
    assert body["source"] == "fallback"
