"""pytest fixtures：每个测试用独立 SQLite 文件 + Flask test client + 已登录用户。"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# 把 backend/ 加到 sys.path，以便 `import db, app` 可用
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture
def temp_db(monkeypatch):
    """每个测试用全新的 SQLite 文件。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DB_FILE", path)
    monkeypatch.setattr("db.DB_FILE", path)
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture
def app(temp_db, monkeypatch):
    """构造一个最小化的 Flask app（不挂 LLM 安全中间件，避免外部依赖）。"""
    monkeypatch.setenv("LOG_DIR", tempfile.mkdtemp())
    # 测试环境提供一个固定 SECRET_KEY，让 services/crypto.py 能派生 Fernet key
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-pytest-only")

    import db as db_mod
    db_mod.init_db()

    from flask import Flask
    from errors import register_error_handlers
    from rate_limit import init_limiter, apply_endpoint_limits

    flask_app = Flask(__name__)
    flask_app.secret_key = "test-secret"
    flask_app.config.update(TESTING=True)
    register_error_handlers(flask_app)
    db_mod.init_app(flask_app)
    init_limiter(flask_app)

    from routes.auth import auth_bp
    from routes.records import records_bp
    from routes.income import income_bp
    from routes.categories import categories_bp
    from routes.budgets import budgets_bp
    from routes.stats import stats_bp
    from routes.admin import admin_bp
    from routes.investment import investment_bp
    from routes.reports import reports_bp
    from routes.export import export_bp
    from routes.health import health_bp
    from routes.recurring import recurring_bp
    from routes.receipts import receipts_bp
    from routes.tips import tips_bp
    from routes.decide import decide_bp

    for bp in [auth_bp, records_bp, income_bp, categories_bp, budgets_bp, stats_bp, admin_bp,
               investment_bp, reports_bp, export_bp, health_bp, recurring_bp, receipts_bp,
               tips_bp, decide_bp]:
        flask_app.register_blueprint(bp)

    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(app, client):
    """注册并登录一个测试用户，返回带 session 的 client。"""
    from werkzeug.security import generate_password_hash
    from db import get_db

    with app.app_context():
        conn = get_db()
        conn.execute(
            "INSERT INTO users (username, password, is_admin) VALUES (?, ?, 0)",
            ("tester", generate_password_hash("pwd")),
        )
        conn.commit()
        uid = conn.execute("SELECT id FROM users WHERE username = ?", ("tester",)).fetchone()[0]

    with client.session_transaction() as s:
        s["user_id"] = uid
        s["username"] = "tester"
    return client
