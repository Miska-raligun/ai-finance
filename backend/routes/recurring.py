"""定期账单 / 重复记账规则 CRUD 路由。

挂在 /api/recurring/*。展开任务不在线上请求中触发（避免 LLM 配额抖动），
仅 scripts/run_recurring.py 定时调用 services.recurring.run_due()。
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from auth import login_required
from db import get_db

recurring_bp = Blueprint("recurring", __name__)

_VALID_KINDS = {"expense", "income"}


@recurring_bp.route("/api/recurring", methods=["GET"])
@login_required
def list_recurring():
    rows = get_db().execute(
        "SELECT id, kind, category, amount, day_of_month, note, active, "
        "last_run_date, created_at, updated_at FROM recurring_rules "
        "WHERE user_id = ? ORDER BY day_of_month ASC, id ASC",
        (g.user_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@recurring_bp.route("/api/recurring", methods=["POST"])
@login_required
def create_recurring():
    data = request.get_json() or {}
    kind = (data.get("kind") or "expense").strip()
    if kind not in _VALID_KINDS:
        return jsonify({"error": "kind 必须是 expense / income"}), 400
    category = (data.get("category") or "").strip()
    if not category:
        return jsonify({"error": "缺少分类"}), 400
    try:
        amount = float(data.get("amount") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "金额必须为数字"}), 400
    if amount <= 0:
        return jsonify({"error": "金额必须大于 0"}), 400
    try:
        day = int(data.get("day_of_month") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "day_of_month 必须为整数"}), 400
    if not 1 <= day <= 31:
        return jsonify({"error": "day_of_month 必须在 1-31 之间"}), 400

    note = (data.get("note") or "").strip() or None
    db = get_db()
    cur = db.execute(
        "INSERT INTO recurring_rules "
        "(user_id, kind, category, amount, day_of_month, note, active, "
        " created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 1, datetime('now'), datetime('now'))",
        (g.user_id, kind, category, amount, day, note),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid, "success": True}), 201


@recurring_bp.route("/api/recurring/<int:rule_id>", methods=["PATCH"])
@login_required
def update_recurring(rule_id: int):
    data = request.get_json() or {}
    allowed = {"kind", "category", "amount", "day_of_month", "note", "active"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({"error": "无可更新字段"}), 400
    if "kind" in updates and updates["kind"] not in _VALID_KINDS:
        return jsonify({"error": "kind 必须是 expense / income"}), 400
    if "day_of_month" in updates:
        try:
            d = int(updates["day_of_month"])
        except (TypeError, ValueError):
            return jsonify({"error": "day_of_month 必须为整数"}), 400
        if not 1 <= d <= 31:
            return jsonify({"error": "day_of_month 必须在 1-31 之间"}), 400
        updates["day_of_month"] = d
    if "amount" in updates:
        try:
            updates["amount"] = float(updates["amount"])
        except (TypeError, ValueError):
            return jsonify({"error": "金额必须为数字"}), 400
        if updates["amount"] <= 0:
            return jsonify({"error": "金额必须大于 0"}), 400
    if "active" in updates:
        updates["active"] = 1 if updates["active"] else 0

    db = get_db()
    res = db.execute(
        "SELECT id FROM recurring_rules WHERE id = ? AND user_id = ?",
        (rule_id, g.user_id),
    ).fetchone()
    if not res:
        return jsonify({"error": "规则不存在"}), 404
    sets = ", ".join(f"{k} = ?" for k in updates) + ", updated_at = datetime('now')"
    values = list(updates.values()) + [rule_id, g.user_id]
    db.execute(f"UPDATE recurring_rules SET {sets} WHERE id = ? AND user_id = ?", values)
    db.commit()
    return jsonify({"success": True})


@recurring_bp.route("/api/recurring/<int:rule_id>", methods=["DELETE"])
@login_required
def delete_recurring(rule_id: int):
    db = get_db()
    res = db.execute(
        "DELETE FROM recurring_rules WHERE id = ? AND user_id = ?",
        (rule_id, g.user_id),
    )
    db.commit()
    if res.rowcount == 0:
        return jsonify({"error": "规则不存在"}), 404
    return jsonify({"success": True})


@recurring_bp.route("/api/recurring/run-now", methods=["POST"])
@login_required
def run_now():
    """手动触发一次展开（仅展开当前用户自己的规则）。

    管理员可在调度未生效或想立刻补单时使用。后台 cron 是面向所有用户的。
    """
    from services.recurring import run_due
    # 只展开当前用户自己的规则,避免一个用户触发全站展开(全量扫描是 cron 的活)。
    result = run_due(user_id=g.user_id)
    return jsonify(result)
