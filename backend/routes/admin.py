"""管理员路由"""
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash
from db import get_db, purge_user_data
from auth import admin_required

logger = logging.getLogger(__name__)

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
    """级联删除用户及其所有业务数据。改用 db.purge_user_data 统一入口，
    新增 investment / reports / risk_profiles 等历史散落的表，避免「删了用户但
    遗留 assets / financial_goals 等孤儿记录」。"""
    data = request.get_json() or {}
    ids = data.get("user_ids") or []
    if not isinstance(ids, list):
        return jsonify({"error": "user_ids 必须是列表"}), 400

    ids = [int(i) for i in ids if isinstance(i, (int, str)) and str(i).isdigit()]
    ids = [i for i in ids if i != session.get("user_id")]
    if not ids:
        return jsonify({"success": True, "purged": {}})

    counts = purge_user_data(ids)
    logger.warning("admin batch_delete by user=%s ids=%s purged=%s",
                   session.get("user_id"), ids, counts)
    return jsonify({"success": True, "purged": counts})


@admin_bp.route("/api/admin/llm-usage", methods=["GET"])
@admin_required
def llm_usage_stats():
    """LLM 用量看板：默认最近 7 天，按日期 + endpoint 聚合。

    查询参数：
      range=7d|30d|all (默认 7d)
    """
    rng = request.args.get("range", "7d")
    db = get_db()
    where = "WHERE 1=1"
    args: list = []
    if rng != "all":
        try:
            days = int(rng.rstrip("d"))
        except ValueError:
            days = 7
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds")
        where += " AND created_at >= ?"
        args.append(cutoff)

    rows = db.execute(
        f"""
        SELECT substr(created_at, 1, 10) as day,
               endpoint,
               model,
               COUNT(*) as calls,
               SUM(prompt_tokens) as prompt_tokens,
               SUM(completion_tokens) as completion_tokens,
               SUM(total_tokens) as total_tokens
        FROM llm_usage
        {where}
        GROUP BY day, endpoint, model
        ORDER BY day DESC, total_tokens DESC
        """,
        args,
    ).fetchall()

    total_row = db.execute(
        f"SELECT COUNT(*) as calls, COALESCE(SUM(total_tokens),0) as total_tokens FROM llm_usage {where}",
        args,
    ).fetchone()

    return jsonify({
        "range": rng,
        "summary": {
            "calls": int(total_row["calls"]),
            "total_tokens": int(total_row["total_tokens"]),
        },
        "rows": [dict(r) for r in rows],
    })
