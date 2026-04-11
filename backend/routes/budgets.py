"""预算管理路由"""
from datetime import datetime
from flask import Blueprint, request, jsonify, g
from db import get_db
from auth import login_required
from constants import CATEGORY_EXPENSE

budgets_bp = Blueprint('budgets', __name__)


@budgets_bp.route('/api/budgets')
@login_required
def get_budgets():
    db = get_db()
    month = request.args.get('month')
    result = []

    if month:
        cursor = db.execute(
            """
            SELECT b.category, b.amount
            FROM budgets b
            JOIN categories c ON b.category = c.name AND c.user_id = b.user_id
            WHERE b.month = ? AND b.user_id = ? AND c.type = ? AND b.amount > 0
        """,
            (month, g.user_id, CATEGORY_EXPENSE)
        )
        budgets = cursor.fetchall()

        cursor = db.execute(
            """
            SELECT category, SUM(amount) as total
            FROM records
            WHERE strftime('%Y-%m', date) = ? AND user_id = ?
            GROUP BY category
        """,
            (month, g.user_id)
        )
        spend_map = {row['category']: row['total'] for row in cursor.fetchall()}

        for b in budgets:
            spent = spend_map.get(b['category'], 0)
            remaining = float(b['amount']) - float(spent)
            result.append({
                'category': b['category'],
                'amount': float(b['amount']),
                'remaining': round(remaining, 2),
                'month': month
            })

    else:
        cursor = db.execute(
            """
            SELECT b.category, b.amount, b.month
            FROM budgets b
            JOIN categories c ON b.category = c.name AND c.user_id = b.user_id
            WHERE b.user_id = ? AND c.type = ? AND b.amount > 0
        """,
            (g.user_id, CATEGORY_EXPENSE)
        )
        all_budgets = cursor.fetchall()

        cursor = db.execute(
            """
            SELECT category, strftime('%Y-%m', date) as month, SUM(amount) as total
            FROM records
            WHERE user_id = ?
            GROUP BY category, month
        """,
            (g.user_id,)
        )
        spend_map = {(row['category'], row['month']): row['total'] for row in cursor.fetchall()}

        for b in all_budgets:
            key = (b['category'], b['month'])
            spent = spend_map.get(key, 0)
            remaining = float(b['amount']) - float(spent)
            result.append({
                'category': b['category'],
                'amount': float(b['amount']),
                'remaining': round(remaining, 2),
                'month': b['month']
            })

    return jsonify(result)


@budgets_bp.route("/api/budgets", methods=["POST"])
@login_required
def set_budget_manual():
    data = request.get_json()
    category = data.get("category", "").strip()
    amount = float(data.get("amount", 0))
    cycle = data.get("cycle", "月")
    month = data.get("month") or datetime.now().strftime('%Y-%m')

    if not category:
        return jsonify({"error": "缺少分类名称"}), 400

    db = get_db()

    row = db.execute(
        "SELECT type FROM categories WHERE name = ? AND user_id = ?",
        (category, g.user_id)
    ).fetchone()
    if not row:
        return jsonify({"error": f"分类「{category}」不存在"}), 400
    if row["type"] != CATEGORY_EXPENSE:
        return jsonify({"error": f"分类「{category}」不是支出类型，无法设置预算"}), 400

    db.execute(
        """
        INSERT OR REPLACE INTO budgets (user_id, category, amount, cycle, month)
        VALUES (?, ?, ?, ?, ?)
    """,
        (g.user_id, category, amount, cycle, month)
    )
    db.commit()
    return jsonify({"success": True})


@budgets_bp.route("/api/budgets", methods=["DELETE"])
@login_required
def delete_budget_manual():
    data = request.get_json()
    category = (data.get("category") or "").strip()
    month = data.get("month") or datetime.now().strftime('%Y-%m')
    if not category:
        return jsonify({"error": "缺少分类名称"}), 400
    db = get_db()
    db.execute(
        "DELETE FROM budgets WHERE user_id = ? AND category = ? AND month = ?",
        (g.user_id, category, month)
    )
    db.commit()
    return jsonify({"success": True})
