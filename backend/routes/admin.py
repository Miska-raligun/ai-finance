"""管理员路由"""
from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash
from db import get_db
from auth import admin_required

admin_bp = Blueprint('admin', __name__)


@admin_bp.route("/api/users", methods=["GET"])
@admin_required
def list_users():
    """列出除当前管理员外的所有用户"""
    db = get_db()
    rows = db.execute(
        "SELECT id, username, is_admin FROM users WHERE id != ?",
        (session.get("user_id"),),
    ).fetchall()
    result = [
        {
            "id": r["id"],
            "username": r["username"],
            "is_admin": bool(r["is_admin"]),
        }
        for r in rows
    ]
    return jsonify(result)


@admin_bp.route("/api/users/<int:user_id>/password", methods=["PUT"])
@admin_required
def admin_change_password(user_id):
    data = request.get_json() or {}
    new_pwd = data.get("password", "").strip()
    if not new_pwd:
        return jsonify({"error": "缺少密码"}), 400
    db = get_db()
    db.execute(
        "UPDATE users SET password = ? WHERE id = ?",
        (generate_password_hash(new_pwd), user_id),
    )
    db.commit()
    return jsonify({"success": True})


@admin_bp.route("/api/users/batch_delete", methods=["POST"])
@admin_required
def admin_batch_delete():
    data = request.get_json() or {}
    ids = data.get("user_ids") or []
    if not isinstance(ids, list):
        return jsonify({"error": "user_ids 必须是列表"}), 400

    ids = [i for i in ids if i != session.get("user_id")]
    if not ids:
        return jsonify({"success": True})

    placeholders = ",".join(["?"] * len(ids))
    db = get_db()
    with db:
        db.execute(f"DELETE FROM users WHERE id IN ({placeholders})", ids)
        db.execute(f"DELETE FROM records WHERE user_id IN ({placeholders})", ids)
        db.execute(f"DELETE FROM income WHERE user_id IN ({placeholders})", ids)
        db.execute(f"DELETE FROM categories WHERE user_id IN ({placeholders})", ids)
        db.execute(f"DELETE FROM budgets WHERE user_id IN ({placeholders})", ids)
        db.execute(f"DELETE FROM llm_config WHERE user_id IN ({placeholders})", ids)
        db.execute(f"DELETE FROM chat_history WHERE user_id IN ({placeholders})", ids)
    return jsonify({"success": True})
