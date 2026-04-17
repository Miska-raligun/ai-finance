from dotenv import load_dotenv
load_dotenv()

# 日志必须最先初始化，确保后续 import 的模块沿用集中配置
from logging_config import setup_logging
setup_logging()

import os
import secrets
from datetime import timedelta
from flask import Flask
from flask_cors import CORS
from db import init_db, init_app, cleanup_all_empty_categories
from llm_security_middleware import register_llm_security
from errors import register_error_handlers
from rate_limit import init_limiter, apply_endpoint_limits

init_db()
cleanup_all_empty_categories()

app = Flask(__name__)
register_llm_security(app)
register_error_handlers(app)
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(16))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
CORS(app, supports_credentials=True)
init_app(app)
init_limiter(app)

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

for bp in [auth_bp, chat_bp, records_bp, income_bp,
           categories_bp, budgets_bp, stats_bp, admin_bp, investment_bp]:
    app.register_blueprint(bp)

# LLM 成本敏感端点的用户级限流（IP 级仍由 llm_security_middleware 兜底）
apply_endpoint_limits(app, {
    "chat.chat": "60/minute",
    "chat.chat_image": "10/minute",
    "chat.commit_record": "120/minute",
    "investment.advisor_chat": "30/minute",
    "investment.submit_risk_quiz": "10/minute",
})

if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=5000)
