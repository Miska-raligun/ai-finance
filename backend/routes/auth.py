"""认证相关路由：验证码、注册、登录、登出、用户信息、LLM配置"""
import base64
from flask import Blueprint, request, jsonify, g, session
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_db
from auth import (
    CAPTCHA_AVAILABLE, login_required, admin_required,
    generate_captcha, validate_captcha,
    login_allowed, record_failure, clear_attempts,
)

auth_bp = Blueprint('auth', __name__)


@auth_bp.route("/api/captcha")
def get_captcha():
    if not CAPTCHA_AVAILABLE:
        return jsonify({'error': 'captcha library not installed, run: pip install captcha'}), 501
    token, chars, img_b64 = generate_captcha()
    return jsonify({'token': token, 'image': 'data:image/png;base64,' + img_b64})


@auth_bp.route("/api/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400

    captcha_token = data.get("captcha_token", "").strip()
    captcha_input = data.get("captcha_input", "").strip()
    ok, err = validate_captcha(captcha_token, captcha_input)
    if not ok:
        return jsonify({"error": err}), 400

    db = get_db()
    cursor = db.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        return jsonify({"error": "用户名已存在"}), 400

    pw_hash = generate_password_hash(password)
    db.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, pw_hash))
    db.commit()
    return jsonify({"success": True})


@auth_bp.route("/api/login", methods=["POST"])
def login():
    ip = request.headers.get("X-Real-IP") or request.remote_addr
    if not login_allowed(ip):
        return jsonify({"error": "登录尝试次数过多，请 30 分钟后再试"}), 429

    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    db = get_db()
    row = db.execute(
        "SELECT id, password, is_admin FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if not row or not check_password_hash(row["password"], password):
        record_failure(ip)
        return jsonify({"error": "用户名或密码错误"}), 400

    clear_attempts(ip)
    session.permanent = bool(data.get("remember", False))
    session["user_id"] = row["id"]
    session["username"] = username
    session["is_admin"] = bool(row["is_admin"])
    return jsonify({"success": True, "is_admin": bool(row["is_admin"])})


@auth_bp.route("/api/logout", methods=["POST"])
@login_required
def logout():
    session.pop("user_id", None)
    session.pop("username", None)
    session.pop("is_admin", None)
    return jsonify({"success": True})


@auth_bp.route("/api/me", methods=["GET"])
@login_required
def get_me():
    """Return current user's basic info."""
    return jsonify(
        {
            "username": session.get("username"),
            "is_admin": bool(session.get("is_admin")),
        }
    )


@auth_bp.route("/api/llm_config", methods=["GET", "POST"])
@login_required
def llm_config_api():
    db = get_db()
    if request.method == "GET":
        row = db.execute(
            "SELECT url, apikey, model, persona FROM llm_config WHERE user_id = ?",
            (g.user_id,),
        ).fetchone()
        return jsonify(dict(row)) if row else jsonify({})

    data = request.get_json() or {}
    url = data.get("url", "").strip()
    apikey = data.get("apikey", "").strip()
    model = data.get("model", "").strip()
    persona = data.get("persona", "").strip()
    db.execute(
        """
        INSERT INTO llm_config (user_id, url, apikey, model, persona)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            url=excluded.url,
            apikey=excluded.apikey,
            model=excluded.model,
            persona=excluded.persona
        """,
        (g.user_id, url, apikey, model, persona),
    )
    db.commit()
    return jsonify({"success": True})


@auth_bp.route("/api/llm_config", methods=["DELETE"])
@login_required
def llm_config_reset():
    db = get_db()
    db.execute("DELETE FROM llm_config WHERE user_id = ?", (g.user_id,))
    db.commit()
    return jsonify({"success": True})
