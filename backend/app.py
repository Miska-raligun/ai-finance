from dotenv import load_dotenv
load_dotenv()

# 日志必须最先初始化，确保后续 import 的模块沿用集中配置
from logging_config import setup_logging
setup_logging()

import os
import sys
import logging
from datetime import timedelta
from flask import Flask
from flask_cors import CORS
from db import init_db, init_app, cleanup_all_empty_categories
from llm_security_middleware import register_llm_security
from errors import register_error_handlers
from rate_limit import init_limiter, apply_endpoint_limits
from csrf import register_csrf

_logger = logging.getLogger(__name__)

# SECRET_KEY 必须通过环境变量提供：临时随机值会让所有 session 在重启后失效，
# 也无法在多进程间共享，对生产环境是隐形的可用性 / 安全风险。
_secret = os.getenv("SECRET_KEY", "").strip()
if not _secret:
    _logger.critical(
        "SECRET_KEY 未配置：请在 backend/.env 中设置（建议 `openssl rand -hex 32`）。"
        " 出于安全考虑拒绝启动。"
    )
    sys.exit(1)
if len(_secret) < 32:
    _logger.warning("SECRET_KEY 长度过短（<32 字符），建议使用 `openssl rand -hex 32` 重新生成。")

# 仅允许显式配置过的来源跨域携带 cookie。开发环境可通过 .env 覆盖。
_origins_env = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
_allowed_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
_cookie_secure = os.getenv("SESSION_COOKIE_SECURE", "0") not in ("0", "false", "False", "")

init_db()
cleanup_all_empty_categories()

app = Flask(__name__)
register_llm_security(app)
register_error_handlers(app)
app.secret_key = _secret
app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=_cookie_secure,
    # 单请求体上限（含 OCR 图片）。可通过环境变量按需放宽。
    MAX_CONTENT_LENGTH=int(os.getenv("MAX_CONTENT_LENGTH_MB", "8")) * 1024 * 1024,
)
CORS(app, supports_credentials=True, origins=_allowed_origins,
     expose_headers=["X-Request-Id", "X-CSRF-Token"])
init_app(app)
init_limiter(app)
register_csrf(app)


# 统一注入安全响应头：浏览器默认即可加固大半 XSS / Clickjacking / MIME-sniff 风险。
_csp_default = (
    "default-src 'self'; "
    "img-src 'self' data: blob:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; "  # Element Plus 等内联样式/脚本兼容
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'"
)
_csp = os.getenv("CONTENT_SECURITY_POLICY", _csp_default)


@app.after_request
def _set_security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Content-Security-Policy", _csp)
    if _cookie_secure:
        resp.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )

    # 只读统计 / 报告端点加 30s 浏览器缓存：用户来回切 tab / 切回应用时
    # 不重发请求（must-revalidate 保证 30s 后会用 If-Modified-Since 重新校验）。
    # 限定 GET 200，避免给错误响应也缓存了。
    from flask import request as _req
    if (resp.status_code == 200 and _req.method == "GET"
            and _req.path.startswith(("/api/stats/", "/api/reports"))
            and not _req.path.endswith("/generate")):
        resp.headers.setdefault("Cache-Control", "private, max-age=30, must-revalidate")

    return resp

# 注册 Blueprints
from routes.auth import auth_bp
from routes.chat import chat_bp
from routes.records import records_bp
from routes.income import income_bp
from routes.categories import categories_bp
from routes.budgets import budgets_bp
from routes.stats import stats_bp
from routes.admin import admin_bp
from routes.investment import investment_bp
from routes.reports import reports_bp
from routes.export import export_bp
from routes.data_import import import_bp
from routes.health import health_bp
from routes.recurring import recurring_bp
from routes.receipts import receipts_bp
from routes.tips import tips_bp
from routes.decide import decide_bp
from routes.checkup import checkup_bp

for bp in [auth_bp, chat_bp, records_bp, income_bp,
           categories_bp, budgets_bp, stats_bp, admin_bp,
           investment_bp, reports_bp, export_bp, import_bp, health_bp,
           recurring_bp, receipts_bp, tips_bp, decide_bp, checkup_bp]:
    app.register_blueprint(bp)

# 启动时一次性收尸：进程崩溃 / 重启会让 reports 表里 pending/running 行永远卡死
# （_inflight 字典仅内存），前端无限轮询。这里标记为 failed 让用户能重新发起。
with app.app_context():
    try:
        from services.reports import cleanup_orphan_reports
        cleanup_orphan_reports()
    except Exception:  # noqa: BLE001
        _logger.exception("启动时清理孤儿 pending/running 报告失败（不阻断启动）")

# LLM 成本敏感端点的用户级限流（IP 级仍由 llm_security_middleware 兜底）
apply_endpoint_limits(app, {
    "chat.chat": "60/minute",
    "chat.chat_image": "10/minute",
    "chat.commit_record": "120/minute",
    "investment.advisor_chat": "30/minute",
    "investment.submit_risk_quiz": "10/minute",
    "reports.api_generate_report": "5/minute",
    "reports.api_recap": "20/minute",
    "checkup.api_compute": "10/minute",
})

if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=5000)
