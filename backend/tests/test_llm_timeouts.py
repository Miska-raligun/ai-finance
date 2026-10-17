"""LLM 超时配置:长输出的调用不能写死短超时。"""


def test_chat_summary_uses_long_timeout(monkeypatch):
    """聊天页的分析类回复(本月分析等)用 LLM_TIMEOUT_LONG,不再写死 30s。"""
    from constants import LLM_TIMEOUT_LONG
    from services import llm

    seen = {}

    def fake_call(messages, **kw):
        seen.update(kw)
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(llm, "_call_llm", fake_call)
    assert llm.call_llm_summary("分析一下我本月的财务状况", "本月支出 100 元") == "ok"
    assert seen["timeout"] == LLM_TIMEOUT_LONG
    assert seen["endpoint"] == "chat.summary"
