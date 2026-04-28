"""CSRF 双重提交 cookie 防护。

机制：
  1. 任何 GET 响应（且当前 cookie 缺失或即将过期时）写入 `csrf_token` cookie
     —— 普通 cookie，可读，写入 SameSite=Lax 即可。
  2. 状态变更请求（POST/PUT/PATCH/DELETE）必须在 `X-CSRF-Token` 头中
     重放该 cookie 的值。攻击者无法读到受害者域下的 cookie，也就无法构造
     合法 header，因此拒绝。
  3. 一些必须不带 cookie 的入口（登录、验证码、注册、健康检查）通过
     `_EXEMPT_PATHS` 放行。

与现有架构的关系：
  - SameSite=Lax 会拦下绝大部分跨域 POST，但仍有可被绕过的边角（顶层导航 +
    form），双重提交是公认的兜底方案。
  - cookie 不是 HttpOnly：前端必须能 document.cookie 读取以放进请求头。
"""
from __future__ import annotations

import logging
import os
import secrets
from flask import Flask, jsonify, request

logger = logging.getLogger(__name__)

_COOKIE_NAME = "csrf_token"
_HEADER_NAME = "X-CSRF-Token"
_TOKEN_BYTES = 32

# 这些路径要么是登录前必须能调用的入口，要么是只读心跳，跳过校验。
# 注意：所有 GET 请求都默认放行，所以只列出 POST 等状态变更端点。
_EXEMPT_PATHS = {
    "/api/login",
    "/api/register",
    "/api/captcha",
    "/api/heartbeat",
}

# 状态变更动词；其余动词（GET/HEAD/OPTIONS）跳过校验。
_PROTECTED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _new_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def register_csrf(app: Flask) -> None:
    enabled = os.getenv("CSRF_ENABLED", "1") not in ("0", "false", "False", "")
    if not enabled:
        logger.warning("CSRF 校验已通过 CSRF_ENABLED=0 关闭，仅建议在内网测试时使用")
        return

    cookie_secure = app.config.get("SESSION_COOKIE_SECURE", False)

    @app.before_request
    def _verify_csrf():
        if request.method not in _PROTECTED_METHODS:
            return
        if request.path in _EXEMPT_PATHS:
            return
        # 仅校验 API；前端静态资源不会涉及状态变更
        if not request.path.startswith("/api/"):
            return

        cookie_token = request.cookies.get(_COOKIE_NAME)
        header_token = request.headers.get(_HEADER_NAME)
        if not cookie_token or not header_token or cookie_token != header_token:
            logger.warning(
                "CSRF rejected: path=%s ip=%s ua=%s",
                request.path,
                request.headers.get("X-Real-IP") or request.remote_addr,
                (request.headers.get("User-Agent") or "")[:80],
            )
            return jsonify({
                "error": "CSRFRejected",
                "code": 403,
                "message": "CSRF 校验失败，请刷新页面后重试",
            }), 403

    @app.after_request
    def _set_csrf_cookie(resp):
        # 仅在 cookie 缺失时下发，避免每次响应都改写浏览器 cookie。
        if not request.cookies.get(_COOKIE_NAME):
            resp.set_cookie(
                _COOKIE_NAME,
                _new_token(),
                max_age=60 * 60 * 24 * 30,
                samesite="Lax",
                secure=cookie_secure,
                httponly=False,  # 前端需要 JS 读取
                path="/",
            )
        return resp
