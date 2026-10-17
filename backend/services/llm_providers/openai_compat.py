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

    def call_stream(self, *, messages, api_key, url, model,
                    temperature=0.5, timeout=60):
        """流式:逐块 yield {"delta": str};结束 yield {"usage": {...}};
        出错 yield {"error": str}。SSE 格式为 `data: {json}` 行 + `data: [DONE]`。"""
        import json
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        payload = {
            "model": model,
            "temperature": temperature,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        try:
            resp = requests.post(url, headers=headers, json=payload,
                                 timeout=timeout, stream=True)
        except requests.exceptions.Timeout:
            yield {"error": f"请求超时（{timeout}s）"}
            return
        except Exception as e:  # noqa: BLE001
            yield {"error": str(e) or "调用异常"}
            return

        if resp.status_code >= 400:
            body = resp.text[:200]
            yield {"error": f"HTTP {resp.status_code}: {body}"}
            return

        # SSE 规定一律 UTF-8,但很多服务只回 `Content-Type: text/event-stream` 不带
        # charset;requests 碰到 text/* 没写 charset 时按 ISO-8859-1 解码,中文就成了
        # "ä½ å¥½" 这种乱码。显式指定。
        resp.encoding = "utf-8"
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data:"):
                continue
            chunk = raw[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                obj = json.loads(chunk)
            except ValueError:
                continue
            choices = obj.get("choices") or []
            if choices:
                d = choices[0].get("delta") or {}
                if d.get("content"):
                    yield {"delta": d["content"]}
                elif d.get("reasoning_content"):
                    # 推理模型先"想"一阵才出正文;不转发想的内容,只报个信,
                    # 让上层能告诉用户"在思考",也让连接不至于长时间没动静
                    yield {"reasoning": True}
            if obj.get("usage"):
                yield {"usage": obj["usage"]}


register(_OpenAICompat())
