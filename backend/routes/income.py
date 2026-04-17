"""收入记录路由"""
from flask import Blueprint, request, jsonify, g
from db import get_db, cleanup_empty_category
from auth import login_required

income_bp = Blueprint('income', __name__)


@income_bp.route('/api/income')
@login_required
def get_income():
    db = get_db()

    try:
        page = max(1, int(request.args.get("page", 1)))
        limit = min(200, max(1, int(request.args.get("limit", 50))))
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

    conditions = ["user_id = ?"]
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
    where = " AND ".join(conditions)

    total = db.execute(f"SELECT COUNT(*) FROM income WHERE {where}", params).fetchone()[0]

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

    return jsonify({"data": results, "total": total, "page": page, "limit": limit})


@income_bp.route('/api/income/<int:income_id>', methods=['DELETE'])
@login_required
def delete_income(income_id):
    db = get_db()
    row = db.execute(
        "SELECT category FROM income WHERE id = ? AND user_id = ?",
        (income_id, g.user_id),
    ).fetchone()
    db.execute(
        "DELETE FROM income WHERE id = ? AND user_id = ?",
        (income_id, g.user_id)
    )
    db.commit()
    if row:
        cleanup_empty_category(g.user_id, row["category"])
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
    return jsonify({"success": True})
