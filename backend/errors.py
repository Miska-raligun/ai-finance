"""全局错误处理 + 请求 ID 注入。

- before_request：为每个请求生成 request_id 并挂到 flask.g
- after_request：把 request_id 写回响应头便于客户端回报
- errorhandler：把异常统一转成 JSON {error, code, request_id}
"""
from __future__ import annotations

import logging
import uuid
from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)
access_logger = logging.getLogger("access")


def _new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def register_error_handlers(app: Flask) -> None:
    @app.before_request
    def _attach_request_id():
        # 客户端可通过 X-Request-Id 复用调用链 ID
        rid = request.headers.get("X-Request-Id") or _new_request_id()
        g.request_id = rid

    @app.after_request
    def _emit_access_log(response):
        rid = getattr(g, "request_id", "-")
        response.headers["X-Request-Id"] = rid
        # 仅记录 API 路径，避免静态资源刷屏
        if request.path.startswith("/api/"):
            access_logger.info(
                "%s %s -> %s", request.method, request.path, response.status_code
            )
        return response

    @app.errorhandler(HTTPException)
    def _handle_http_exc(e: HTTPException):
        rid = getattr(g, "request_id", "-")
        # 401/403/404 视为正常业务流，不打 error 日志
        if e.code and e.code >= 500:
            logger.exception("HTTPException %s on %s", e.code, request.path)
        return (
            jsonify(
                {
                    "error": e.name,
                    "message": e.description,
                    "code": e.code,
                    "request_id": rid,
                }
            ),
            e.code or 500,
        )

    @app.errorhandler(Exception)
    def _handle_unhandled(e: Exception):
        rid = getattr(g, "request_id", "-")
        logger.exception("Unhandled exception on %s: %s", request.path, e)
        return (
            jsonify(
                {
                    "error": "InternalServerError",
                    "message": "服务器内部错误，请稍后重试或联系管理员",
                    "code": 500,
                    "request_id": rid,
                }
            ),
            500,
        )
