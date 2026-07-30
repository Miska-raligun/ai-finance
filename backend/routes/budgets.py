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
              AND deleted_at IS NULL
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
            WHERE user_id = ? AND deleted_at IS NULL
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


@budgets_bp.route('/api/budgets/calibrate', methods=['GET'])
@login_required
def calibrate_budgets():
    """基于过去 3 个月的平均消费，建议下月每个分类的预算。

    公式：建议预算 = ceil(round(过去 3 个月该分类总支出 / 实际月数, 0) * inflation)
    inflation = 1.05（默认 5% 缓冲，应对偶发大额支出）

    Query: month=YYYY-MM 默认本月+1（即下月）；inflation=float 默认 1.05

    返回 {target_month, items: [{category, avg_spend_3m, current_budget,
    suggested_budget, delta_pct}], total_suggested}
    """
    import math
    target = (request.args.get("month") or "").strip()
    if not target:
        # 默认建议"下月"
        today = datetime.now()
        year, mon = today.year, today.month
        target = f"{year + 1}-01" if mon == 12 else f"{year}-{mon + 1:02d}"
    if len(target) != 7:
        return jsonify({"error": "month 格式应为 YYYY-MM"}), 400

    try:
        infl = float(request.args.get("inflation") or 1.05)
    except (TypeError, ValueError):
        infl = 1.05
    infl = max(0.5, min(infl, 2.0))  # clamp 防止滥用

    db = get_db()
    # 过去 3 个完整月（不含 target 当月）
    rows = db.execute(
        """
        SELECT category,
               SUM(amount) AS total,
               COUNT(DISTINCT strftime('%Y-%m', date)) AS active_months
        FROM records
        WHERE user_id = ?
          AND deleted_at IS NULL
          AND strftime('%Y-%m', date) < ?
          AND strftime('%Y-%m', date) >= strftime('%Y-%m', date(?, '-3 months'))
        GROUP BY category
        ORDER BY total DESC
        """,
        (g.user_id, target, target + "-01"),
    ).fetchall()

    # 当前 target 月已有预算
    current_budgets = {
        r["category"]: float(r["amount"])
        for r in db.execute(
            "SELECT category, amount FROM budgets WHERE user_id = ? AND month = ?",
            (g.user_id, target),
        ).fetchall()
    }

    items = []
    total_suggested = 0.0
    for r in rows:
        active = max(1, int(r["active_months"] or 1))
        avg = float(r["total"]) / active
        suggested = math.ceil(avg * infl)
        current = current_budgets.get(r["category"], 0)
        delta_pct = None
        if current > 0:
            delta_pct = round((suggested - current) / current * 100, 1)
        items.append({
            "category": r["category"],
            "avg_spend_3m": round(avg, 2),
            "active_months": active,
            "current_budget": current,
            "suggested_budget": suggested,
            "delta_pct": delta_pct,
        })
        total_suggested += suggested

    return jsonify({
        "target_month": target,
        "inflation": infl,
        "items": items,
        "total_suggested": round(total_suggested, 2),
    })


@budgets_bp.route('/api/budgets/calibrate/apply', methods=['POST'])
@login_required
def apply_calibration():
    """批量应用一组建议预算到指定月份。

    Body: {month, items: [{category, suggested_budget}]}
    """
    data = request.get_json() or {}
    month = (data.get("month") or "").strip()
    items = data.get("items") or []
    if len(month) != 7:
        return jsonify({"error": "month 格式应为 YYYY-MM"}), 400
    if not isinstance(items, list) or not items:
        return jsonify({"error": "items 必须是非空列表"}), 400

    db = get_db()
    applied = 0
    for it in items:
        cat = (it.get("category") or "").strip()
        try:
            amt = float(it.get("suggested_budget") or 0)
        except (TypeError, ValueError):
            continue
        if not cat or amt <= 0:
            continue
        # 分类不存在则跳过（避免静默建错分类）
        ok = db.execute(
            "SELECT 1 FROM categories WHERE user_id = ? AND name = ? AND type = ?",
            (g.user_id, cat, CATEGORY_EXPENSE),
        ).fetchone()
        if not ok:
            continue
        db.execute(
            "INSERT OR REPLACE INTO budgets (user_id, category, amount, cycle, month) "
            "VALUES (?, ?, ?, '月', ?)",
            (g.user_id, cat, amt, month),
        )
        applied += 1
    db.commit()
    return jsonify({"success": True, "applied": applied, "month": month})
