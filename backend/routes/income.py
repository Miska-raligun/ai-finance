"""收入记录路由"""
from flask import Blueprint, request, jsonify, g
from db import get_db, cleanup_empty_category
from auth import login_required
from cache import invalidate_user

income_bp = Blueprint('income', __name__)


@income_bp.route('/api/income')
@login_required
def get_income():
    db = get_db()

    try:
        page = max(1, int(request.args.get("page", 1)))
        # 与 records 一致的 100 条硬上限，避免一次性返回过多导致前端卡顿
        limit = min(100, max(1, int(request.args.get("limit", 50))))
    except (ValueError, TypeError):
        page, limit = 1, 50
    offset = (page - 1) * limit

    sort_by = request.args.get("sort_by", "date")
    sort_order = request.args.get("sort_order", "DESC").upper()
    if sort_by not in ("date", "amount"):
        sort_by = "date"
    if sort_order not in ("ASC", "DESC"):
        sort_order = "DESC"

    category = request.args.get("category")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    month = request.args.get("month")
    if month and not start_date and not end_date:
        import calendar as _cal
        y, m = map(int, month.split('-'))
        start_date = f"{month}-01"
        end_date = f"{month}-{_cal.monthrange(y, m)[1]:02d}"

    conditions = ["user_id = ?", "deleted_at IS NULL"]
    params = [g.user_id]
    if category:
        conditions.append("category = ?")
        params.append(category)
    if start_date:
        conditions.append("date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date)
    # 关键词搜索,与 records 一致:note / category 模糊匹配,转义通配符
    q_kw = (request.args.get("q") or "").strip()
    if q_kw:
        esc = q_kw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(r"(note LIKE ? ESCAPE '\' OR category LIKE ? ESCAPE '\')")
        params.extend([f"%{esc}%", f"%{esc}%"])
    where = " AND ".join(conditions)

    # 条数 + 合计一次算完;合计始终对应当前筛选范围(与 records 一致)
    total_row = db.execute(
        f"SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM income WHERE {where}", params
    ).fetchone()
    total, sum_amount = total_row[0], round(float(total_row[1]), 2)

    rows = db.execute(
        f"SELECT id, category, amount, note, date, strftime('%Y-%m', date) as month "
        f"FROM income WHERE {where} ORDER BY {sort_by} {sort_order}, id DESC LIMIT ? OFFSET ?",
        params + [limit, offset]
    ).fetchall()

    results = []
    for row in rows:
        r = dict(row)
        if not r.get("date"):
            r["date"] = (r.get("month") or "") + "-01"
        results.append(r)

    return jsonify({"data": results, "total": total, "sum_amount": sum_amount,
                    "page": page, "limit": limit})


@income_bp.route('/api/income/<int:income_id>', methods=['DELETE'])
@login_required
def delete_income(income_id):
    """软删除,与 records 一致,支持撤销;过期软删行由每日 cron 物理清理。"""
    from db import soft_delete
    hit = soft_delete("income", user_id=g.user_id, row_id=income_id)
    invalidate_user(g.user_id)
    return jsonify({"success": True, "undoable": hit})


@income_bp.route('/api/income/<int:income_id>/restore', methods=['POST'])
@login_required
def restore_income(income_id):
    db = get_db()
    cur = db.execute(
        "UPDATE income SET deleted_at = NULL "
        "WHERE id = ? AND user_id = ? AND deleted_at IS NOT NULL",
        (income_id, g.user_id),
    )
    db.commit()
    if cur.rowcount == 0:
        return jsonify({"success": False, "error": "记录不存在或未被删除"}), 404
    invalidate_user(g.user_id)
    return jsonify({"success": True})


@income_bp.route('/api/income/<int:income_id>', methods=['PUT'])
@login_required
def update_income(income_id):
    data = request.get_json()
    category = data.get('category', '').strip()
    amount = float(data.get('amount', 0))
    note = data.get('note', '').strip()
    date = data.get('date')
    db = get_db()
    old_row = db.execute(
        "SELECT category FROM income WHERE id = ? AND user_id = ?",
        (income_id, g.user_id),
    ).fetchone()
    db.execute(
        "UPDATE income SET category = ?, amount = ?, note = ?, date = ? WHERE id = ? AND user_id = ?",
        (category, amount, note, date, income_id, g.user_id),
    )
    db.commit()
    if old_row and old_row["category"] != category:
        cleanup_empty_category(g.user_id, old_row["category"])
    invalidate_user(g.user_id)
    return jsonify({"success": True})
