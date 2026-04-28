"""理财目标 CRUD。"""
from __future__ import annotations

from flask import g, jsonify, request

from auth import login_required
from db import get_db

from ._common import investment_bp, now_iso


@investment_bp.route("/api/investment/goals", methods=["GET"])
@login_required
def list_goals():
    rows = get_db().execute(
        "SELECT * FROM financial_goals WHERE user_id = ? ORDER BY priority ASC, deadline ASC",
        (g.user_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@investment_bp.route("/api/investment/goals", methods=["POST"])
@login_required
def create_goal():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "缺少目标名称"}), 400
    try:
        target = float(data.get("target_amount") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "target_amount 必须为数字"}), 400
    if target <= 0:
        return jsonify({"error": "target_amount 必须大于 0"}), 400

    db = get_db()
    cur = db.execute(
        "INSERT INTO financial_goals (user_id, name, target_amount, deadline, "
        "current_progress, priority, note, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            g.user_id, name, target,
            (data.get("deadline") or "").strip() or None,
            float(data.get("current_progress") or 0),
            int(data.get("priority") or 3),
            (data.get("note") or "").strip() or None,
            now_iso(), now_iso(),
        ),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid, "success": True}), 201


@investment_bp.route("/api/investment/goals/<int:goal_id>", methods=["PATCH"])
@login_required
def update_goal(goal_id: int):
    data = request.get_json() or {}
    allowed = {"name", "target_amount", "deadline", "current_progress", "priority", "note"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({"error": "无可更新字段"}), 400

    db = get_db()
    res = db.execute(
        "SELECT id FROM financial_goals WHERE id = ? AND user_id = ?",
        (goal_id, g.user_id),
    ).fetchone()
    if not res:
        return jsonify({"error": "目标不存在"}), 404

    sets = ", ".join(f"{k} = ?" for k in updates) + ", updated_at = ?"
    values = list(updates.values()) + [now_iso(), goal_id, g.user_id]
    db.execute(f"UPDATE financial_goals SET {sets} WHERE id = ? AND user_id = ?", values)
    db.commit()
    return jsonify({"success": True})


@investment_bp.route("/api/investment/goals/<int:goal_id>", methods=["DELETE"])
@login_required
def delete_goal(goal_id: int):
    db = get_db()
    res = db.execute(
        "DELETE FROM financial_goals WHERE id = ? AND user_id = ?",
        (goal_id, g.user_id),
    )
    db.commit()
    if res.rowcount == 0:
        return jsonify({"error": "目标不存在"}), 404
    return jsonify({"success": True})
