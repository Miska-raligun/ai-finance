"""LLM 流式:stream_llm 逐段产出、上游 SSE 解码,以及聊天回复的后台作业(边写边轮询)。"""
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


# ---------- 聊天回复:后台作业 + 轮询 ----------

import time


@pytest.fixture
def chat_client(app, auth_client):
    """conftest 没注册 chat_bp(避免常规测试拉 MCP 依赖),这里单独挂上。"""
    from routes.chat import chat_bp
    app.register_blueprint(chat_bp)
    return auth_client


def _drain(client, job_id, timeout=8.0):
    """像前端那样按 since 轮询到结束。
    返回 (拼起来的增量, 见过的进度提示, 见过的 meta, 终态记录, 是否中途拿到过正文)。"""
    got, statuses, metas, partial = "", [], [], False
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/chat/jobs/{job_id}?since={len(got)}")
        assert r.status_code == 200, r.get_json()
        job = r.get_json()
        if job["status"] in ("done", "failed", "cancelled"):
            return got, statuses, metas, job, partial
        assert job["status"] in ("pending", "running"), job   # 进度提示不能盖掉作业状态
        if job.get("length", 0) > len(got):
            got += job["text"]
            partial = True
        if job.get("meta"):
            metas.append(job["meta"])
        if job.get("step"):
            statuses.append(job["step"])
        time.sleep(0.02)
    raise AssertionError("作业没在时限内结束")


def _intent_with_tool(name="budget_remain", args="{}"):
    return {"choices": [{"message": {"tool_calls": [
        {"id": "1", "type": "function", "function": {"name": name, "arguments": args}}]}}]}


def _slow(pieces, delay=0.05):
    def gen(*a, **kw):
        for p in pieces:
            time.sleep(delay)
            yield p
    return gen


def test_chat_async_tool_then_summary(chat_client, monkeypatch):
    """快捷按钮那条路:提交立刻拿 job_id,分析边写边能取到,写完整段存进历史。"""
    monkeypatch.setattr("routes.chat.call_llm_intent", lambda *a, **kw: _intent_with_tool())
    monkeypatch.setattr("routes.chat._process_tool_calls",
                        lambda tc, cfg: (["本月餐饮预算剩 300 元"], [], [], []))
    import services.llm as llm_mod
    monkeypatch.setattr("services.llm.stream_llm_summary",
                        _slow([llm_mod.THINKING, "餐饮", "还剩 ", "300 元。"]))

    r = chat_client.post("/api/chat/async", json={"message": "查询本月各分类预算余额"})
    assert r.status_code == 202
    got, steps, _, job, partial = _drain(chat_client, r.get_json()["job_id"])
    assert job["status"] == "done"
    assert "正在分析…" in steps                                   # 正文出来之前有进度提示
    assert job["result"]["reply"] == "餐饮还剩 300 元。"
    assert partial and job["result"]["reply"].startswith(got)   # 中途就拿到过一部分

    hist = chat_client.get("/api/chat/history").get_json()
    assert hist[-2]["content"] == "查询本月各分类预算余额"
    assert hist[-1] == {"role": "assistant", "content": "餐饮还剩 300 元。"}


def test_chat_async_pending_cards_arrive_early(chat_client, monkeypatch):
    rec = {"type": "expense", "category": "餐饮", "amount": 20, "date": "2026-10-17", "note": ""}
    monkeypatch.setattr("routes.chat.call_llm_intent", lambda *a, **kw: _intent_with_tool("add_record"))
    monkeypatch.setattr("routes.chat._process_tool_calls",
                        lambda tc, cfg: (["已识别一笔支出"], [rec], [], []))
    monkeypatch.setattr("services.llm.stream_llm_summary", _slow(["记", "好", "啦"], delay=0.1))

    job_id = chat_client.post("/api/chat/async", json={"message": "吃饭20"}).get_json()["job_id"]
    _, _, metas, job, _ = _drain(chat_client, job_id)
    assert metas and metas[0]["pending_records"] == [rec]       # 写完之前卡片就到了
    assert job["result"]["pending_records"] == [rec]


def test_chat_async_freeform(chat_client, monkeypatch):
    monkeypatch.setattr("routes.chat.call_llm_intent",
                        lambda *a, **kw: {"choices": [{"message": {"content": None}}]})
    monkeypatch.setattr("services.llm.stream_llm_chat", lambda *a, **kw: iter(["哈喽", "～"]))
    job_id = chat_client.post("/api/chat/async", json={"message": "哈喽"}).get_json()["job_id"]
    assert _drain(chat_client, job_id)[3]["result"]["reply"] == "哈喽～"


def test_chat_async_quota(chat_client, monkeypatch):
    monkeypatch.setattr("routes.chat.call_llm_intent",
                        lambda *a, **kw: {"error": {"code": "quota_exceeded", "message": "x"}})
    job_id = chat_client.post("/api/chat/async", json={"message": "hi"}).get_json()["job_id"]
    assert "额度已用完" in _drain(chat_client, job_id)[3]["result"]["reply"]


def test_chat_async_failure_is_reported(chat_client, monkeypatch):
    """意图识别就超时了:作业 failed 并带原因(前端显示在气泡里),历史里也存了。"""
    monkeypatch.setattr("routes.chat.call_llm_intent",
                        lambda *a, **kw: {"error": {"message": "请求超时（10s）"}})
    job_id = chat_client.post("/api/chat/async", json={"message": "分析一下"}).get_json()["job_id"]
    job = _drain(chat_client, job_id)[3]
    assert job["status"] == "failed" and "请求超时" in job["error"]
    assert "请求超时" in chat_client.get("/api/chat/history").get_json()[-1]["content"]


def test_chat_async_cancel(chat_client, monkeypatch):
    monkeypatch.setattr("routes.chat.call_llm_intent",
                        lambda *a, **kw: {"choices": [{"message": {"content": None}}]})
    monkeypatch.setattr("services.llm.stream_llm_chat", _slow(["字"] * 200, delay=0.02))
    job_id = chat_client.post("/api/chat/async", json={"message": "hi"}).get_json()["job_id"]
    time.sleep(0.2)
    assert chat_client.post(f"/api/chat/jobs/{job_id}/cancel").get_json()["success"]
    assert _drain(chat_client, job_id)[3]["status"] == "cancelled"


def test_chat_async_rejects_empty(chat_client):
    assert chat_client.post("/api/chat/async", json={"message": "  "}).status_code == 400


def test_chat_jobs_endpoint_only_serves_chat_kinds(app, chat_client):
    """/api/chat/jobs 只给聊天类作业用,别的作业(比如行程生成)从这里查不到。"""
    from services import ai_jobs
    ai_jobs.register("_test_other", lambda ctx: {"x": 1})
    with app.test_request_context():
        from flask import g
        g.user_id = 1
        other = ai_jobs.submit(1, "_test_other", {}, None)
    assert chat_client.get(f"/api/chat/jobs/{other}").status_code == 404


def test_job_live_since_offset(app):
    """live(job, since) 只回 since 之后新增的字。"""
    from services import ai_jobs
    ctx = ai_jobs.JobCtx(987654, 1, "chat_reply", {}, None, None)
    ctx.set_status("正在查账…")
    ctx.say("你好，")
    ctx.say("世界")
    snap = ai_jobs.live(987654, since=3)
    assert snap == {"text": "世界", "length": 5, "step": "正在查账…", "meta": {}}
    ai_jobs._live.pop(987654, None)


# ---------- 投资顾问 ----------

def test_advisor_async_general(app, chat_client, monkeypatch):
    monkeypatch.setattr("services.llm.stream_advisor_chat",
                        _slow(["根据你的持仓，", "建议均衡配置。"]))
    r = chat_client.post("/api/investment/advisor/chat/async",
                         json={"history": [{"role": "user", "content": "怎么配"}]})
    assert r.status_code == 202
    assert _drain(chat_client, r.get_json()["job_id"])[3]["result"]["reply"] == "根据你的持仓，建议均衡配置。"


def test_advisor_async_requires_history(chat_client):
    assert chat_client.post("/api/investment/advisor/chat/async", json={"history": []}).status_code == 400


def test_advisor_async_portfolio(chat_client, monkeypatch):
    monkeypatch.setattr("routes.investment.advisor.fetch_assets",
                        lambda: [{"type": "股票", "amount": 100}])
    monkeypatch.setattr("routes.investment.advisor.compute_allocation", lambda a: {})
    monkeypatch.setattr("routes.investment.advisor.compute_return", lambda a: {})
    monkeypatch.setattr("routes.investment.advisor.build_holding_details", lambda a: [])
    monkeypatch.setattr("services.llm.stream_portfolio_advice",
                        lambda *a, **kw: iter(["持仓偏股，", "注意分散。"]))
    job_id = chat_client.post("/api/investment/advisor/chat/async",
                              json={"mode": "portfolio"}).get_json()["job_id"]
    assert _drain(chat_client, job_id)[3]["result"]["reply"] == "持仓偏股，注意分散。"


def test_advisor_async_portfolio_without_assets(chat_client, monkeypatch):
    monkeypatch.setattr("routes.investment.advisor.fetch_assets", lambda: [])
    job_id = chat_client.post("/api/investment/advisor/chat/async",
                              json={"mode": "portfolio"}).get_json()["job_id"]
    assert "请先在资产列表中添加持仓" in _drain(chat_client, job_id)[3]["result"]["reply"]
