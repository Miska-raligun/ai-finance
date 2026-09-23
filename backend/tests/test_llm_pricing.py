"""LLM 模型单价匹配 + 成本估算。"""


def test_deepseek_chat_pricing():
    from services.llm_pricing import estimate_cost_usd
    # 100k prompt + 50k completion；DeepSeek chat 0.27/1.10 per 1M
    cost = estimate_cost_usd("deepseek-chat", 100_000, 50_000)
    expected = round(100_000 * 0.27 / 1e6 + 50_000 * 1.10 / 1e6, 6)
    assert abs(cost - expected) < 1e-6


def test_claude_sonnet_pricing():
    from services.llm_pricing import estimate_cost_usd
    cost = estimate_cost_usd("claude-sonnet-4-5", 10_000, 5_000)
    expected = round(10_000 * 3.0 / 1e6 + 5_000 * 15.0 / 1e6, 6)
    assert abs(cost - expected) < 1e-6


def test_gemini_flash_pricing():
    from services.llm_pricing import estimate_cost_usd
    cost = estimate_cost_usd("gemini-2.5-flash", 1_000_000, 1_000_000)
    # 0.075 + 0.30 = 0.375
    assert abs(cost - 0.375) < 0.001


def test_ollama_local_zero_cost():
    from services.llm_pricing import estimate_cost_usd
    assert estimate_cost_usd("llama-3-8b", 5000, 5000) == 0.0


def test_unknown_model_falls_back():
    """未识别的模型走兜底 1/3 USD per 1M，避免估算偏低。"""
    from services.llm_pricing import estimate_cost_usd
    cost = estimate_cost_usd("some-future-model-xyz", 1_000_000, 1_000_000)
    # fallback: 1.0 + 3.0 = 4.0
    assert abs(cost - 4.0) < 0.001


def test_empty_model_returns_fallback():
    from services.llm_pricing import estimate_cost_usd
    cost = estimate_cost_usd("", 1_000_000, 0)
    assert abs(cost - 1.0) < 0.001


def test_zero_tokens_zero_cost():
    from services.llm_pricing import estimate_cost_usd
    assert estimate_cost_usd("claude-opus-4", 0, 0) == 0.0
