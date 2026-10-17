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


# ---------- 乱码:上游 SSE 不带 charset ----------

def _fake_sse_response(lines: list[str], content_type="text/event-stream"):
    """造一个 requests.Response:正文是 UTF-8 字节,Content-Type 不写 charset。"""
    import io
    import requests
    r = requests.models.Response()
    r.status_code = 200
    r.headers["Content-Type"] = content_type
    r.raw = io.BytesIO("".join(l + "\n\n" for l in lines).encode("utf-8"))
    return r


def test_openai_stream_decodes_utf8_without_charset(monkeypatch):
    """上游只回 text/event-stream 不带 charset 时,中文不能被当 ISO-8859-1 解成乱码。"""
    import json
    from services.llm_providers.openai_compat import _OpenAICompat

    chunks = ["你好，", "这是投资建议"]
    lines = [f"data: {json.dumps({'choices': [{'delta': {'content': c}}]}, ensure_ascii=False)}"
             for c in chunks] + ["data: [DONE]"]
    monkeypatch.setattr("requests.post", lambda *a, **kw: _fake_sse_response(lines))

    out = [ev["delta"] for ev in _OpenAICompat().call_stream(
        messages=[], api_key="k", url="http://x", model="m") if "delta" in ev]
    assert "".join(out) == "你好，这是投资建议"


def test_openai_stream_reports_reasoning(monkeypatch):
    import json
    from services.llm_providers.openai_compat import _OpenAICompat

    lines = [f"data: {json.dumps({'choices': [{'delta': {'reasoning_content': '想一想'}}]}, ensure_ascii=False)}",
             f"data: {json.dumps({'choices': [{'delta': {'content': '答案'}}]}, ensure_ascii=False)}",
             "data: [DONE]"]
    monkeypatch.setattr("requests.post", lambda *a, **kw: _fake_sse_response(lines))
    evs = list(_OpenAICompat().call_stream(messages=[], api_key="k", url="http://x", model="m"))
    assert evs == [{"reasoning": True}, {"delta": "答案"}]   # 思考内容本身不转发


def test_stream_llm_thinking_marker_only_when_asked(app, monkeypatch):
    import services.llm as llm

    class _Reasoner:
        name = "openai"
        def call_stream(self, **kw):
            yield {"reasoning": True}
            yield {"reasoning": True}     # 2 秒内的第二次不再报
            yield {"delta": "好"}

    monkeypatch.setattr("services.llm_providers.resolve", lambda name: _Reasoner())
    with app.app_context():
        plain = list(llm.stream_llm([], llm={"apikey": "k"}, endpoint="t"))
        marked = list(llm.stream_llm([], llm={"apikey": "k"}, endpoint="t", with_thinking=True))
    assert plain == ["好"]
    assert marked == [llm.THINKING, "好"]


# ---------- 共用 SSE 工具 ----------

def test_with_heartbeat_pings_while_waiting(app):
    import time
    from flask import g
    from services.sse import HEARTBEAT, with_heartbeat

    def gen():
        result = yield from with_heartbeat(lambda: (time.sleep(0.35), g.user_id)[1], interval=0.1)
        yield ("result", result)

    with app.test_request_context():
        g.user_id = 42
        out = list(gen())
    assert out[-1] == ("result", 42)          # 后台线程里也拿得到 g.user_id
    assert out.count(HEARTBEAT) >= 2


def test_with_heartbeat_reraises(app):
    from services.sse import with_heartbeat

    def boom():
        raise ValueError("坏了")

    def gen():
        yield from with_heartbeat(boom, interval=0.05)

    with app.test_request_context():
        with pytest.raises(ValueError):
            list(gen())


def _events(body: str):
    import json
    out = []
    for block in body.split("\n\n"):
        block = block.strip()
        if block.startswith("data:") and block[5:].strip() != "[DONE]":
            out.append(json.loads(block[5:].strip()))
    return out


# ---------- /api/chat/stream ----------

@pytest.fixture
def chat_client(app, auth_client):
    """conftest 没注册 chat_bp(避免常规测试拉 MCP 依赖),这里单独挂上。"""
    from routes.chat import chat_bp
    app.register_blueprint(chat_bp)
    return auth_client


def _intent_with_tool(name="query_budget", args="{}"):
    return {"choices": [{"message": {"tool_calls": [
        {"id": "1", "type": "function", "function": {"name": name, "arguments": args}}]}}]}


def test_chat_stream_tool_then_streamed_summary(chat_client, monkeypatch):
    """快捷按钮那条路:调工具 → 总结逐段推送,并且整段回复存进历史。"""
    monkeypatch.setattr("routes.chat.call_llm_intent", lambda *a, **kw: _intent_with_tool())
    monkeypatch.setattr("routes.chat._process_tool_calls",
                        lambda tc, cfg: (["本月餐饮预算剩 300 元"], [], [], []))

    def fake_summary(user_msg, result, llm=None):
        import services.llm as llm_mod
        yield llm_mod.THINKING
        yield "餐饮还剩 "
        yield "300 元。"

    monkeypatch.setattr("services.llm.stream_llm_summary", fake_summary)

    r = chat_client.post("/api/chat/stream", json={"message": "查询本月各分类预算余额"})
    assert r.status_code == 200 and "text/event-stream" in r.content_type
    body = r.get_data(as_text=True)
    evs = _events(body)
    assert "".join(e.get("delta", "") for e in evs) == "餐饮还剩 300 元。"
    assert {"status": "正在查账…"} in evs and {"status": "正在分析…"} in evs
    assert body.rstrip().endswith("data: [DONE]")

    hist = chat_client.get("/api/chat/history").get_json()
    assert hist[-2]["content"] == "查询本月各分类预算余额"
    assert hist[-1] == {"role": "assistant", "content": "餐饮还剩 300 元。"}


def test_chat_stream_pushes_pending_cards(chat_client, monkeypatch):
    rec = {"type": "expense", "category": "餐饮", "amount": 20, "date": "2026-10-17", "note": ""}
    monkeypatch.setattr("routes.chat.call_llm_intent", lambda *a, **kw: _intent_with_tool("add_record"))
    monkeypatch.setattr("routes.chat._process_tool_calls",
                        lambda tc, cfg: (["已识别一笔支出"], [rec], [], []))
    monkeypatch.setattr("services.llm.stream_llm_summary", lambda *a, **kw: iter(["记好啦"]))

    evs = _events(chat_client.post("/api/chat/stream", json={"message": "吃饭20"}).get_data(as_text=True))
    meta = [e["meta"] for e in evs if "meta" in e]
    assert meta == [{"pending_records": [rec], "pending_assets": [], "pending_goals": []}]


def test_chat_stream_freeform(chat_client, monkeypatch):
    """没调工具也没内容 → 闲聊,同样流式。"""
    monkeypatch.setattr("routes.chat.call_llm_intent",
                        lambda *a, **kw: {"choices": [{"message": {"content": None}}]})
    monkeypatch.setattr("services.llm.stream_llm_chat", lambda *a, **kw: iter(["哈喽", "～"]))
    evs = _events(chat_client.post("/api/chat/stream", json={"message": "哈喽"}).get_data(as_text=True))
    assert "".join(e.get("delta", "") for e in evs) == "哈喽～"


def test_chat_stream_quota(chat_client, monkeypatch):
    monkeypatch.setattr("routes.chat.call_llm_intent",
                        lambda *a, **kw: {"error": {"code": "quota_exceeded", "message": "x"}})
    evs = _events(chat_client.post("/api/chat/stream", json={"message": "hi"}).get_data(as_text=True))
    assert "额度已用完" in "".join(e.get("delta", "") for e in evs)


def test_chat_stream_error_midway_still_finishes(chat_client, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("上游炸了")
    monkeypatch.setattr("routes.chat.call_llm_intent", boom)
    body = chat_client.post("/api/chat/stream", json={"message": "hi"}).get_data(as_text=True)
    assert {"error": "生成中断，请重试。"} in _events(body)
    assert body.rstrip().endswith("data: [DONE]")


def test_chat_stream_rejects_empty(chat_client):
    assert chat_client.post("/api/chat/stream", json={"message": "  "}).status_code == 400


# ---------- 一键诊断持仓也走流式 ----------

def test_advisor_stream_portfolio_mode(app, auth_client, monkeypatch):
    monkeypatch.setattr("routes.investment.advisor.fetch_assets",
                        lambda: [{"type": "股票", "amount": 100}])
    monkeypatch.setattr("routes.investment.advisor.compute_allocation", lambda a: {})
    monkeypatch.setattr("routes.investment.advisor.compute_return", lambda a: {})
    monkeypatch.setattr("routes.investment.advisor.build_holding_details", lambda a: [])
    monkeypatch.setattr("services.llm.stream_portfolio_advice",
                        lambda *a, **kw: iter(["持仓偏股，", "注意分散。"]))
    evs = _events(auth_client.post("/api/investment/advisor/chat/stream",
                                   json={"mode": "portfolio"}).get_data(as_text=True))
    assert "".join(e.get("delta", "") for e in evs) == "持仓偏股，注意分散。"


def test_advisor_stream_portfolio_without_assets(app, auth_client, monkeypatch):
    monkeypatch.setattr("routes.investment.advisor.fetch_assets", lambda: [])
    evs = _events(auth_client.post("/api/investment/advisor/chat/stream",
                                   json={"mode": "portfolio"}).get_data(as_text=True))
    assert "请先在资产列表中添加持仓" in "".join(e.get("delta", "") for e in evs)
