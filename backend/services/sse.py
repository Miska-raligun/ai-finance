"""聊天类接口共用的 SSE(Server-Sent Events)输出。

记账聊天和投资顾问都走这一套,前端也只有一份解析(utils/chatStream.js)。
每个事件一行 `data: {json}`,事件之间空一行,最后 `data: [DONE]`:

    {"delta": "文本增量"}            正文,前端直接往气泡里追加
    {"status": "正在查账…"}          进度提示,正文出来之前显示
    {"meta": {...}}                  非文本的附加数据,比如待确认卡片
    {"error": "说明"}                出错;正文已经出来一部分时前端照样保留

另有不带数据的心跳(SSE 注释行 `: ping`),前端解析时直接忽略。它的用处是
让连接一直有数据:Nginx 的 proxy_read_timeout、Cloudflare 都会掐掉"太久
没动静"的连接,而意图识别、调工具、推理模型的思考阶段都可能好几十秒不出字。
"""
from __future__ import annotations

import json
import logging
import threading

from flask import Response, current_app, g, stream_with_context

logger = logging.getLogger(__name__)


class _Heartbeat:
    __slots__ = ()


HEARTBEAT = _Heartbeat()
HEARTBEAT_EVERY = 10   # 秒


def _encode(ev) -> str:
    if ev is HEARTBEAT:
        return ": ping\n\n"
    return f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"


def sse_response(events) -> Response:
    """把一个产出事件 dict(或 HEARTBEAT)的生成器包成 SSE 响应。
    生成器里抛异常不会让连接直接断掉:转成一个 error 事件,照常收尾。"""

    @stream_with_context
    def _gen():
        try:
            for ev in events:
                yield _encode(ev)
        except Exception:  # noqa: BLE001
            logger.exception("SSE 生成中断")
            yield _encode({"error": "生成中断，请重试。"})
        yield "data: [DONE]\n\n"

    return Response(_gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             # 让 Nginx 收到一段就转一段,别攒满缓冲区才发
                             "X-Accel-Buffering": "no"})


def with_heartbeat(fn, *, interval: float = HEARTBEAT_EVERY):
    """在后台线程里跑一个阻塞调用,等待期间每隔 interval 秒产出一次 HEARTBEAT。

    用法(在事件生成器里):  result = yield from with_heartbeat(lambda: slow())
    fn 在新的 app context 里跑,g.user_id 会带过去(handler 依赖它);
    fn 里的异常原样抛回调用方。
    """
    app = current_app._get_current_object()
    user_id = getattr(g, "user_id", None)
    box: dict = {}

    def run():
        with app.app_context():
            if user_id is not None:
                g.user_id = user_id
            try:
                box["value"] = fn()
            except BaseException as e:  # noqa: BLE001  原样带回调用方
                box["error"] = e

    t = threading.Thread(target=run, name="sse-blocking", daemon=True)
    t.start()
    while True:
        t.join(interval)
        if not t.is_alive():
            break
        yield HEARTBEAT
    if "error" in box:
        raise box["error"]
    return box.get("value")


def relay_text(pieces, *, thinking_status: str = "思考中…"):
    """把 stream_llm 一类的产出转成事件:文本 → delta,THINKING → status。
    返回值(yield from 拿到)是拼好的完整正文。"""
    from services.llm import THINKING

    parts: list[str] = []
    for piece in pieces:
        if piece is THINKING:
            # 已经开始出正文就不再提示"思考中",只当心跳
            yield HEARTBEAT if parts else {"status": thinking_status}
        elif piece:
            parts.append(piece)
            yield {"delta": piece}
    return "".join(parts)
