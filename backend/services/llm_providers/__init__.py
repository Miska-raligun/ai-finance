"""LLM provider 抽象层。

不同厂商的 API schema 差异很大（OpenAI / Anthropic / Gemini ...），但上层
business code 一直按 OpenAI 兼容格式写。Provider 的职责：

  1. 把 OpenAI 风格的入参（messages + tools + tool_choice + temperature）
     转成厂商 native 格式
  2. 把厂商 native 响应转成 OpenAI 兼容格式：
        {
          "choices": [{"message": {"content": str|None,
                                   "tool_calls": [{"id", "type": "function",
                                                   "function": {"name", "arguments"}}]}}],
          "usage": {"prompt_tokens", "completion_tokens", "total_tokens"}
        }
     或失败时返回 {"error": {"message": str, ...}}

这样 services/llm.py 与 handlers / routes 不需要为每个 provider 写适配。
"""
from __future__ import annotations

from typing import Protocol


class LLMProvider(Protocol):
    name: str

    def call(
        self,
        *,
        messages: list[dict],
        api_key: str,
        url: str,
        model: str,
        tools: list | None = None,
        tool_choice: str | None = None,
        temperature: float = 0.3,
        timeout: int = 10,
    ) -> dict:
        ...


# 注册表 + 名称归一化
_REGISTRY: dict[str, LLMProvider] = {}


def register(provider: LLMProvider) -> None:
    _REGISTRY[provider.name] = provider


def resolve(name: str | None) -> LLMProvider:
    """按名称获取 provider；缺省 / 不识别走 OpenAI 兼容。"""
    key = (name or "openai").strip().lower()
    if key in {"", "openai", "openai_compat", "deepseek", "siliconflow",
              "qwen", "kimi", "moonshot", "zhipu", "glm", "ollama", "groq",
              "together"}:
        key = "openai"
    if key not in _REGISTRY:
        # 不抛错，让用户体验稳——回退默认 provider，日志会有
        return _REGISTRY["openai"]
    return _REGISTRY[key]


# Eager-load builtin providers 以注册到 _REGISTRY
from . import openai_compat as _o  # noqa: E402,F401
from . import anthropic as _a  # noqa: E402,F401
from . import gemini as _g  # noqa: E402,F401
