"""LLM provider 适配层单测：覆盖入参 → native 格式、native 响应 → OpenAI 格式。

只测纯转换函数，不实际打外部 API；网络层留给端到端测试。
"""
import json


def test_resolve_falls_back_to_openai_for_unknown():
    from services.llm_providers import resolve
    p = resolve("nonexistent-provider")
    assert p.name == "openai"


def test_resolve_aliases():
    from services.llm_providers import resolve
    for alias in ("deepseek", "siliconflow", "qwen", "kimi", "moonshot",
                  "zhipu", "glm", "ollama", "groq", "together", ""):
        assert resolve(alias).name == "openai"
    assert resolve("anthropic").name == "anthropic"
    assert resolve("gemini").name == "gemini"


def test_anthropic_split_system_and_messages():
    from services.llm_providers.anthropic import _split_system
    sys, rest = _split_system([
        {"role": "system", "content": "今天是 2025-04-29"},
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好"},
    ])
    assert "2025-04-29" in sys and "你是助手" in sys
    assert len(rest) == 2 and rest[0]["role"] == "user"


def test_anthropic_convert_tools_to_native_schema():
    from services.llm_providers.anthropic import _convert_tools
    out = _convert_tools([
        {"type": "function",
         "function": {"name": "add_record", "description": "记一笔",
                      "parameters": {"type": "object",
                                     "properties": {"amount": {"type": "number"}}}}}
    ])
    assert out[0]["name"] == "add_record"
    assert out[0]["input_schema"]["properties"]["amount"]["type"] == "number"


def test_anthropic_response_to_openai_with_text_and_tool_use():
    from services.llm_providers.anthropic import _to_openai_response
    out = _to_openai_response({
        "content": [
            {"type": "text", "text": "好的，我来帮你记账。"},
            {"type": "tool_use", "id": "tu_1", "name": "add_record",
             "input": {"分类": "餐饮", "金额": 12.5}},
        ],
        "usage": {"input_tokens": 30, "output_tokens": 12},
    })
    msg = out["choices"][0]["message"]
    assert "好的" in msg["content"]
    tc = msg["tool_calls"][0]
    assert tc["function"]["name"] == "add_record"
    assert json.loads(tc["function"]["arguments"])["金额"] == 12.5
    assert out["usage"]["total_tokens"] == 42


def test_gemini_convert_messages_extracts_system():
    from services.llm_providers.gemini import _convert_messages
    sys, contents = _convert_messages([
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "Hi"},
    ])
    assert sys == "你是助手"
    assert contents[0]["role"] == "user"
    assert contents[1]["role"] == "model"
    assert contents[1]["parts"][0]["text"] == "Hi"


def test_gemini_response_to_openai_with_function_call():
    from services.llm_providers.gemini import _to_openai_response
    out = _to_openai_response({
        "candidates": [{"content": {"parts": [
            {"text": "好的"},
            {"functionCall": {"name": "add_record",
                              "args": {"分类": "餐饮", "金额": 12.5}}},
        ]}}],
        "usageMetadata": {"promptTokenCount": 30, "candidatesTokenCount": 8,
                          "totalTokenCount": 38},
    })
    msg = out["choices"][0]["message"]
    assert msg["content"] == "好的"
    assert msg["tool_calls"][0]["function"]["name"] == "add_record"
    assert out["usage"]["total_tokens"] == 38


def test_gemini_blocked_response_returns_error():
    from services.llm_providers.gemini import _to_openai_response
    out = _to_openai_response({
        "candidates": [],
        "promptFeedback": {"blockReason": "SAFETY"},
    })
    assert "error" in out
    assert "SAFETY" in out["error"]["message"]


def test_dispatch_uses_correct_provider(monkeypatch):
    """services/llm._call_llm 把 provider 字段正确路由到对应 provider。"""
    monkeypatch.setenv("SECRET_KEY", "x" * 64)
    from services.llm_providers import resolve

    seen = {}

    class _Stub:
        name = "anthropic"
        def call(self, **kw):
            seen.update(kw)
            return {"choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}

    # 临时把 anthropic 替换成桩
    from services import llm_providers as registry_mod
    real = registry_mod._REGISTRY["anthropic"]
    registry_mod._REGISTRY["anthropic"] = _Stub()
    try:
        from services.llm import _call_llm
        result = _call_llm(
            [{"role": "user", "content": "hi"}],
            llm={"provider": "anthropic", "apikey": "k", "url": "u", "model": "m"},
            endpoint="test",
        )
        assert "choices" in result
        assert seen["api_key"] == "k"
        assert seen["model"] == "m"
    finally:
        registry_mod._REGISTRY["anthropic"] = real
