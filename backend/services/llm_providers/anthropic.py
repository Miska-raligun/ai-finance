"""Anthropic Claude provider。

差异点：
  * 端点：`POST {url}/v1/messages`（用户填基础 url，例如
    https://api.anthropic.com，缺省补全协议路径）
  * 鉴权：`x-api-key` + `anthropic-version: 2023-06-01`
  * `system` 必须从 messages 中分离出来
  * tools schema 使用 `{name, description, input_schema}`
  * tool_choice：`{type: "auto"|"any"}` 或 `{type: "tool", name: "x"}`
  * 响应 content 是 block 数组：`[{type: "text"|"tool_use", ...}]`
  * usage 字段名：`input_tokens` / `output_tokens`

Provider 内部把这些差异都抹平，对外仍输出 OpenAI 兼容格式。
"""
from __future__ import annotations

import json
import logging
from typing import Any

import requests

from . import register

logger = logging.getLogger(__name__)

_DEFAULT_BASE = "https://api.anthropic.com"
_VERSION = "2023-06-01"
# Claude 的 messages API 必须显式给一个 max_tokens；给一个对常用任务足够大的默认。
_DEFAULT_MAX_TOKENS = 4096


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """把所有 role=system 的 content 合并成单一 system 字符串，剩余消息保留顺序。"""
    sys_parts: list[str] = []
    rest: list[dict] = []
    for m in messages:
        if m.get("role") == "system":
            content = m.get("content")
            if isinstance(content, str) and content:
                sys_parts.append(content)
            continue
        # Anthropic 仅识别 "user" / "assistant"；同 role 连续也能接受
        rest.append({"role": m["role"], "content": m.get("content") or ""})
    return "\n\n".join(sys_parts), rest


def _convert_tools(tools: list[dict] | None) -> list[dict] | None:
    """OpenAI tools → Anthropic tools。"""
    if not tools:
        return None
    out = []
    for t in tools:
        fn = t.get("function") or {}
        out.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    return out


def _convert_tool_choice(tc: str | dict | None) -> dict | None:
    if not tc:
        return None
    if tc == "auto" or tc == "any":
        return {"type": tc}
    if tc == "none":
        return None  # Anthropic 用 "auto" 时不调工具就是 none 等效
    if isinstance(tc, dict):
        # OpenAI 风格 {"type": "function", "function": {"name": "x"}} → {"type": "tool", "name": "x"}
        if tc.get("type") == "function":
            name = (tc.get("function") or {}).get("name")
            if name:
                return {"type": "tool", "name": name}
    return {"type": "auto"}


def _to_openai_response(data: dict) -> dict:
    """Anthropic response → OpenAI 兼容 {choices, usage}。"""
    blocks = data.get("content") or []
    text_parts: list[str] = []
    tool_calls: list[dict] = []
    for i, b in enumerate(blocks):
        btype = b.get("type")
        if btype == "text":
            t = b.get("text") or ""
            if t:
                text_parts.append(t)
        elif btype == "tool_use":
            tool_calls.append({
                "id": b.get("id") or f"call_{i}",
                "type": "function",
                "function": {
                    "name": b.get("name", ""),
                    "arguments": json.dumps(b.get("input") or {}, ensure_ascii=False),
                },
            })

    msg: dict[str, Any] = {"content": "\n".join(text_parts) or None}
    if tool_calls:
        msg["tool_calls"] = tool_calls

    usage = data.get("usage") or {}
    prompt = int(usage.get("input_tokens") or 0)
    completion = int(usage.get("output_tokens") or 0)
    return {
        "choices": [{"message": msg}],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        },
    }


class _Anthropic:
    name = "anthropic"

    def call(self, *, messages, api_key, url, model, tools=None,
             tool_choice=None, temperature=0.3, timeout=10):
        # 用户在 url 字段填 base URL（不带 /v1/messages 也行）
        base = (url or "").strip().rstrip("/") or _DEFAULT_BASE
        if not base.endswith("/messages"):
            base = base + ("/messages" if base.endswith("/v1") else "/v1/messages")

        system, rest = _split_system(messages)
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": _DEFAULT_MAX_TOKENS,
            "temperature": temperature,
            "messages": rest,
        }
        if system:
            body["system"] = system
        a_tools = _convert_tools(tools)
        if a_tools:
            body["tools"] = a_tools
        a_tc = _convert_tool_choice(tool_choice)
        if a_tc:
            body["tool_choice"] = a_tc

        headers = {
            "x-api-key": api_key,
            "anthropic-version": _VERSION,
            "Content-Type": "application/json",
        }

        try:
            res = requests.post(base, headers=headers, json=body, timeout=timeout)
        except requests.exceptions.Timeout:
            return {"error": {"message": f"请求超时（{timeout}s）"}}
        except Exception as e:  # noqa: BLE001
            return {"error": {"message": str(e) or "调用异常"}}

        try:
            data = res.json()
        except ValueError:
            return {"error": {"message": f"HTTP {res.status_code} 非 JSON 响应"}}

        if res.status_code >= 400 or data.get("type") == "error":
            err = data.get("error") or {"message": f"HTTP {res.status_code}"}
            return {"error": err if isinstance(err, dict) else {"message": str(err)}}
        return _to_openai_response(data)


register(_Anthropic())
