"""Google Gemini provider。

差异点：
  * 端点：`POST {base}/v1beta/models/{model}:generateContent?key={api_key}`
  * 鉴权走 query string（非 header）
  * 角色：user / model（不是 user / assistant）
  * system 走 `systemInstruction.parts[].text`
  * tools schema：`[{functionDeclarations: [{name, description, parameters}]}]`
  * tool_choice 通过 `toolConfig.functionCallingConfig.mode` (AUTO / ANY / NONE)
  * 响应：candidates[0].content.parts[] 每个 part 是 {text} 或 {functionCall}
  * usage 字段：promptTokenCount / candidatesTokenCount / totalTokenCount
"""
from __future__ import annotations

import json
import logging
import uuid

import requests

from . import register

logger = logging.getLogger(__name__)

_DEFAULT_BASE = "https://generativelanguage.googleapis.com"


def _convert_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """OpenAI messages → (systemInstruction text, contents[])。"""
    sys_parts: list[str] = []
    contents: list[dict] = []
    for m in messages:
        role = m.get("role")
        text = m.get("content") or ""
        if role == "system":
            if isinstance(text, str) and text:
                sys_parts.append(text)
            continue
        # OpenAI assistant → Gemini model；user / tool → user
        gem_role = "model" if role == "assistant" else "user"
        contents.append({"role": gem_role, "parts": [{"text": text}]})
    return "\n\n".join(sys_parts), contents


def _convert_tools(tools: list[dict] | None) -> list[dict] | None:
    if not tools:
        return None
    decls = []
    for t in tools:
        fn = t.get("function") or {}
        decls.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    return [{"functionDeclarations": decls}] if decls else None


def _convert_tool_choice(tc: str | dict | None) -> dict | None:
    if tc in (None, "none"):
        return None
    if tc == "auto":
        return {"functionCallingConfig": {"mode": "AUTO"}}
    if tc == "any" or tc == "required":
        return {"functionCallingConfig": {"mode": "ANY"}}
    if isinstance(tc, dict) and tc.get("type") == "function":
        name = (tc.get("function") or {}).get("name")
        if name:
            return {"functionCallingConfig": {
                "mode": "ANY", "allowedFunctionNames": [name],
            }}
    return {"functionCallingConfig": {"mode": "AUTO"}}


def _to_openai_response(data: dict) -> dict:
    cands = data.get("candidates") or []
    if not cands:
        # 触发了 safety 拦截或为空响应
        reason = (data.get("promptFeedback") or {}).get("blockReason")
        if reason:
            return {"error": {"message": f"Gemini 拒绝：{reason}"}}
        return {"choices": [{"message": {"content": ""}}], "usage": {}}

    parts = ((cands[0] or {}).get("content") or {}).get("parts") or []
    text_parts: list[str] = []
    tool_calls: list[dict] = []
    for p in parts:
        if "text" in p and p["text"]:
            text_parts.append(p["text"])
        elif "functionCall" in p:
            fc = p["functionCall"] or {}
            tool_calls.append({
                "id": "call_" + uuid.uuid4().hex[:10],
                "type": "function",
                "function": {
                    "name": fc.get("name", ""),
                    "arguments": json.dumps(fc.get("args") or {}, ensure_ascii=False),
                },
            })

    msg: dict = {"content": "\n".join(text_parts) or None}
    if tool_calls:
        msg["tool_calls"] = tool_calls

    usage = data.get("usageMetadata") or {}
    prompt = int(usage.get("promptTokenCount") or 0)
    completion = int(usage.get("candidatesTokenCount") or 0)
    total = int(usage.get("totalTokenCount") or (prompt + completion))
    return {
        "choices": [{"message": msg}],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
        },
    }


class _Gemini:
    name = "gemini"

    def call(self, *, messages, api_key, url, model, tools=None,
             tool_choice=None, temperature=0.3, timeout=10):
        base = (url or "").strip().rstrip("/") or _DEFAULT_BASE
        # 兼容用户填 https://...:generateContent 全 url 的情况
        if ":generateContent" in base:
            endpoint = f"{base}?key={api_key}"
        else:
            endpoint = f"{base}/v1beta/models/{model}:generateContent?key={api_key}"

        system, contents = _convert_messages(messages)
        body: dict = {
            "contents": contents,
            "generationConfig": {"temperature": temperature},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        g_tools = _convert_tools(tools)
        if g_tools:
            body["tools"] = g_tools
        g_tc = _convert_tool_choice(tool_choice)
        if g_tc:
            body["toolConfig"] = g_tc

        try:
            res = requests.post(endpoint, headers={"Content-Type": "application/json"},
                                json=body, timeout=timeout)
        except requests.exceptions.Timeout:
            return {"error": {"message": f"请求超时（{timeout}s）"}}
        except Exception as e:  # noqa: BLE001
            return {"error": {"message": str(e) or "调用异常"}}

        try:
            data = res.json()
        except ValueError:
            return {"error": {"message": f"HTTP {res.status_code} 非 JSON 响应"}}

        if res.status_code >= 400:
            err = data.get("error") if isinstance(data, dict) else None
            return {"error": err or {"message": f"HTTP {res.status_code}"}}
        return _to_openai_response(data)


register(_Gemini())
