"""Anon 小贴士端点 /api/anon/tip：永远 200，LLM 失败回退本地池。"""


def test_tip_endpoint_returns_200_without_llm(auth_client):
    """没配 LLM key 时直接走 fallback，不应调用 LLM。"""
    r = auth_client.get("/api/anon/tip")
    assert r.status_code == 200
    body = r.get_json()
    assert "tip" in body
    assert body["source"] == "fallback"
    assert 1 <= len(body["tip"]) <= 40


def test_tip_endpoint_requires_login(client):
    r = client.get("/api/anon/tip")
    assert r.status_code == 401


def test_tip_endpoint_falls_back_on_llm_failure(auth_client, monkeypatch):
    """LLM 调用抛异常时仍 200 + source=fallback。"""
    from services.llm_config import save_llm_config
    from flask import g
    with auth_client.application.app_context():
        with auth_client.session_transaction() as s:
            uid = s["user_id"]
        # 给 user 配一个 key 让端点尝试调 LLM
        save_llm_config(uid, url="https://invalid.example",
                        apikey="sk-test", model="x", persona="")

    def _boom(*a, **kw):
        raise RuntimeError("simulated")
    monkeypatch.setattr("services.llm._call_llm", _boom)

    r = auth_client.get("/api/anon/tip")
    assert r.status_code == 200
    body = r.get_json()
    assert body["source"] == "fallback"
