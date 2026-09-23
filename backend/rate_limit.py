"""Flask-Limiter 用户级限流。

与 llm_security_middleware 的 IP 级限流互补：
- 这里按 user_id 限流，专门保护 LLM 成本敏感端点
- 未登录请求按 IP 兜底
"""
from __future__ import annotations

import logging
from flask import Flask, jsonify, session, request, g

logger = logging.getLogger(__name__)

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    _AVAILABLE = True
except ImportError:
    Limiter = None  # type: ignore
    _AVAILABLE = False


def _key_func():
    """登录用户按 user_id；未登录按 IP。"""
    uid = session.get("user_id")
    if uid:
        return f"user:{uid}"
    return f"ip:{request.headers.get('X-Real-IP') or request.remote_addr or 'unknown'}"


limiter = None


def init_limiter(app: Flask):
    global limiter
    if not _AVAILABLE:
        logger.warning("flask-limiter 未安装，跳过用户级限流（可执行：pip install flask-limiter）")
        return None
    limiter = Limiter(
        key_func=_key_func,
        app=app,
        default_limits=[],  # 默认不全局限流，按需在端点上加装饰器
        storage_uri="memory://",
        strategy="fixed-window",
    )

    @app.errorhandler(429)
    def _ratelimit_handler(e):
        rid = getattr(g, "request_id", "-")
        logger.warning("rate limit exceeded: %s on %s", _key_func(), request.path)
        return (
            jsonify(
                {
                    "error": "RateLimitExceeded",
                    "message": "请求过于频繁，请稍后再试",
                    "code": 429,
                    "request_id": rid,
                }
            ),
            429,
        )

    return limiter


def apply_endpoint_limits(app: Flask, rules: dict[str, str]) -> None:
    """对一组 endpoint 应用限流规则。

    用法：
        apply_endpoint_limits(app, {
            "chat.chat": "60/minute",
            "chat.chat_image": "10/minute",
        })

    需要在所有 blueprint 注册后调用。
    """
    if limiter is None:
        return
    for endpoint, rule in rules.items():
        view = app.view_functions.get(endpoint)
        if view is None:
            logger.warning("限流配置：未找到端点 %s，跳过", endpoint)
            continue
        # 必须把包装后的 view 写回 app.view_functions——否则 Flask 派发的仍然是
        # 原始函数,flask-limiter 在 before_request 钩子里走 in_middleware=True
        # 路径,而该路径只对 _endpoint_hints 里有映射的 endpoint 才会展开装饰
        # 限流,导致这里加的规则全部静默失效。
        app.view_functions[endpoint] = limiter.limit(rule)(view)
