"""按模型估算 LLM 成本（USD）。

价格表来自各厂商公开页（截至 2026-04）。匹配规则：模型名前缀大小写不敏感
匹配，未命中走最保守的 fallback 单价（避免估算偏低）。

输入 prompt_tokens / completion_tokens 是 OpenAI 兼容字段，每个 provider 在
adapter 内部已经统一到这两个数字。

人民币用户参考：1 USD ≈ 7 CNY，前端展示时再换算。
"""
from __future__ import annotations

# 单价：USD / 1M tokens（input, output）
# 注：DeepSeek / SiliconFlow / Qwen / Kimi / 智谱 是国内服务，单价更低；
# Anthropic / OpenAI / Gemini 直连贵不少。下面按模型名前缀匹配，命中即用。
_PRICE_TABLE: list[tuple[str, float, float]] = [
    # --- DeepSeek ---
    ("deepseek-chat",     0.27, 1.10),
    ("deepseek-reasoner", 0.55, 2.19),
    ("deepseek-v3",       0.27, 1.10),
    ("deepseek-r1",       0.55, 2.19),
    # --- SiliconFlow 常见模型（DeepSeek 镜像更便宜）---
    ("pro/deepseek",      0.27, 1.10),
    ("qwen2",             0.28, 0.85),
    ("qwen3",             0.28, 0.85),
    # --- Kimi / Moonshot ---
    ("moonshot-v1",       0.50, 1.40),
    ("kimi",              0.50, 1.40),
    # --- 智谱 GLM ---
    ("glm-4",             0.85, 2.10),
    ("glm-4-flash",       0.07, 0.21),
    # --- Anthropic Claude ---
    ("claude-opus-4",     15.00, 75.00),
    ("claude-opus",       15.00, 75.00),
    ("claude-sonnet-4-5", 3.00, 15.00),
    ("claude-sonnet-4",   3.00, 15.00),
    ("claude-sonnet",     3.00, 15.00),
    ("claude-haiku-4-5",  1.00, 5.00),
    ("claude-haiku",      0.80, 4.00),
    ("claude-3.5-sonnet", 3.00, 15.00),
    ("claude-3.5-haiku",  0.80, 4.00),
    ("claude-3-opus",    15.00, 75.00),
    ("claude-3-sonnet",   3.00, 15.00),
    ("claude-3-haiku",    0.25, 1.25),
    # --- OpenAI ---
    ("gpt-4o-mini",       0.15, 0.60),
    ("gpt-4o",            2.50, 10.00),
    ("gpt-4-turbo",      10.00, 30.00),
    ("gpt-4",            30.00, 60.00),
    ("gpt-3.5",           0.50, 1.50),
    ("o1",               15.00, 60.00),
    # --- Google Gemini ---
    ("gemini-2.5-pro",    1.25, 5.00),
    ("gemini-2.5-flash",  0.075, 0.30),
    ("gemini-2.0-flash",  0.075, 0.30),
    ("gemini-1.5-pro",    1.25, 5.00),
    ("gemini-1.5-flash",  0.075, 0.30),
    # --- Ollama / 本地 -> 0 ---
    ("llama",             0.0, 0.0),
    ("ollama",            0.0, 0.0),
]

# 未命中模型的兜底单价（USD/1M），偏保守（贵）；宁愿高估也别低估
_FALLBACK_INPUT = 1.0
_FALLBACK_OUTPUT = 3.0


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """按模型名前缀匹配定价表，估算 USD 成本。

    与真实账单可能有 5%~20% 偏差（模型版本细分、缓存命中折扣等未建模），
    用作"今日大致花了多少美金"的看板足够。
    """
    if not model:
        return _calc(prompt_tokens, completion_tokens, _FALLBACK_INPUT, _FALLBACK_OUTPUT)
    key = model.strip().lower()
    for prefix, in_price, out_price in _PRICE_TABLE:
        if key.startswith(prefix.lower()) or prefix.lower() in key:
            return _calc(prompt_tokens, completion_tokens, in_price, out_price)
    return _calc(prompt_tokens, completion_tokens, _FALLBACK_INPUT, _FALLBACK_OUTPUT)


def _calc(p_tokens: int, c_tokens: int, in_per_m: float, out_per_m: float) -> float:
    return round(p_tokens * in_per_m / 1_000_000 + c_tokens * out_per_m / 1_000_000, 6)
