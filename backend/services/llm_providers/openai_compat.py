"""OpenAI 兼容 provider：DeepSeek / SiliconFlow / Qwen / Kimi / 智谱 / Ollama /
OpenAI 本身 等所有走 /chat/completions 协议的服务。

这是默认 provider；上层调用直接传 OpenAI schema 入参，响应也已经是 OpenAI
兼容格式，因此 adapter 几乎是透传。"""
from __future__ import annotations

import logging

import requests

from . import register

logger = logging.getLogger(__name__)


class _OpenAICompat:
    name = "openai"

    def call(self, *, messages, api_key, url, model, tools=None,
             tool_choice=None, temperature=0.3, timeout=10):
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "model": model,
            "temperature": temperature,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice

        try:
            res = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except requests.exceptions.Timeout:
            return {"error": {"message": f"请求超时（{timeout}s）"}}
        except Exception as e:  # noqa: BLE001
            return {"error": {"message": str(e) or "调用异常"}}

        try:
            data = res.json()
        except ValueError:
            return {"error": {"message": f"HTTP {res.status_code} 非 JSON 响应"}}

        if "error" in data:
            return data
        if res.status_code >= 400:
            return {"error": {"message": f"HTTP {res.status_code}"}}
        return data


register(_OpenAICompat())
