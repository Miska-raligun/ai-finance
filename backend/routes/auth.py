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
    from services.llm_config import get_llm_config, save_llm_config, public_view
    if request.method == "GET":
        # 对外只下发掩码后的 apikey，避免明文泄漏
        return jsonify(public_view(get_llm_config(g.user_id)))

    data = request.get_json() or {}
    save_llm_config(
        g.user_id,
        url=data.get("url", ""),
        apikey=data.get("apikey", ""),
        model=data.get("model", ""),
        persona=data.get("persona", ""),
    )
    return jsonify({"success": True})


@auth_bp.route("/api/llm_config", methods=["DELETE"])
@login_required
def llm_config_reset():
    db = get_db()
    db.execute("DELETE FROM llm_config WHERE user_id = ?", (g.user_id,))
    db.commit()
    return jsonify({"success": True})


@auth_bp.route("/api/me/delete", methods=["POST"])
@login_required
def delete_self():
    """GDPR / 账号注销：删除当前用户全部数据并清 session。

    需要二次确认：请求体必须 {"confirm": "DELETE"}。
    管理员账号需要先把 admin 权限交给别人，否则拒绝以避免锁死后台。
    """
    import logging
    from db import purge_user_data

    data = request.get_json(silent=True) or {}
    if data.get("confirm") != "DELETE":
        return jsonify({
            "error": "需要确认",
            "message": "请在请求体中提供 {\"confirm\": \"DELETE\"} 以确认注销",
        }), 400

    uid = g.user_id
    if session.get("is_admin"):
        # 管理员注销前必须确保还有别的管理员，避免无人能进 admin 后台
        db = get_db()
        other = db.execute(
            "SELECT COUNT(*) FROM users WHERE is_admin = 1 AND id != ?",
            (uid,),
        ).fetchone()[0]
        if other == 0:
            return jsonify({
                "error": "最后一个管理员",
                "message": "你是当前唯一的管理员，请先把 admin 权限交给其他用户后再注销",
            }), 409

    counts = purge_user_data([uid])
    logging.getLogger(__name__).warning(
        "user self-deletion uid=%s purged=%s", uid, counts
    )
    session.clear()
    return jsonify({"success": True, "purged": counts})
