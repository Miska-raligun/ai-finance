"""LLM 流式:stream_llm 逐段产出 + advisor SSE 端点。"""
from __future__ import annotations

import pytest


def test_stream_llm_yields_deltas(app, monkeypatch):
    import services.llm as llm

    class _FakeProvider:
        name = "openai"
        def call_stream(self, **kw):
            yield {"delta": "你好"}
            yield {"delta": "，世界"}
            yield {"usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}}

    monkeypatch.setattr("services.llm_providers.resolve", lambda name: _FakeProvider())
    with app.app_context():
        out = "".join(llm.stream_llm([{"role": "user", "content": "hi"}],
                                     llm={"apikey": "k"}, endpoint="test"))
    assert out == "你好，世界"


def test_stream_llm_fallback_when_no_call_stream(app, monkeypatch):
    """provider 没有 call_stream(如 anthropic)时退回一次性,整段吐出。"""
    import services.llm as llm

    class _NoStream:
        name = "anthropic"
        def call(self, **kw):
            return {"choices": [{"message": {"content": "整段回复"}}],
                    "usage": {"total_tokens": 4}}

    monkeypatch.setattr("services.llm_providers.resolve", lambda name: _NoStream())
    with app.app_context():
        out = "".join(llm.stream_llm([{"role": "user", "content": "hi"}],
                                     llm={"apikey": "k"}, endpoint="test"))
    assert out == "整段回复"


def test_advisor_stream_endpoint_sse(app, auth_client, monkeypatch):
    from routes.investment import investment_bp  # noqa: F401 ensure registered

    def _fake_stream(history, context=None, llm=None):
        yield "根据你的持仓，"
        yield "建议均衡配置。"

    monkeypatch.setattr("services.llm.stream_advisor_chat", _fake_stream)

    r = auth_client.post("/api/investment/advisor/chat/stream",
                         json={"history": [{"role": "user", "content": "怎么配"}]})
    assert r.status_code == 200
    assert "text/event-stream" in r.content_type
    body = r.get_data(as_text=True)
    assert "根据你的持仓，" in body
    assert "建议均衡配置。" in body
    assert "[DONE]" in body


def test_advisor_stream_requires_history(app, auth_client):
    r = auth_client.post("/api/investment/advisor/chat/stream", json={"history": []})
    assert r.status_code == 400
