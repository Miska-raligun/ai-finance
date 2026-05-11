"""支出记录路由"""
from flask import Blueprint, request, jsonify, g
from constants import PARAM_AMOUNT, PARAM_CATEGORY, PARAM_DATE, PARAM_NOTE
from db import get_db, cleanup_empty_category
from auth import login_required
from cache import invalidate_user

records_bp = Blueprint('records', __name__)


def _load_llm_cfg() -> dict:
    from services.llm_config import get_llm_config
    return get_llm_config(g.user_id) or {}


@records_bp.route('/api/records')
@login_required
def get_records():
    db = get_db()

    try:
        page = max(1, int(request.args.get("page", 1)))
        # 单次最多 100 条；超出会让前端渲染明显卡顿，分页是更可控的解决方案
        limit = min(100, max(1, int(request.args.get("limit", 50))))
    except (ValueError, TypeError):
        page, limit = 1, 50
    offset = (page - 1) * limit

    sort_by = request.args.get("sort_by", "date")
    sort_order = request.args.get("sort_order", "DESC").upper()
    allowed_sort = {"date", "amount", "left_budget"}
    if sort_by not in allowed_sort:
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

    outer_conditions = []
    outer_params = []
    if category:
        outer_conditions.append("category = ?")
        outer_params.append(category)
    if start_date:
        outer_conditions.append("date >= ?")
        outer_params.append(start_date)
    if end_date:
        outer_conditions.append("date <= ?")
        outer_params.append(end_date)
    outer_where = ("WHERE " + " AND ".join(outer_conditions)) if outer_conditions else ""

    total = db.execute(
        f"""
        WITH base AS (SELECT id, category, date FROM records WHERE user_id = ?)
        SELECT COUNT(*) FROM base {outer_where}
        """,
        [g.user_id] + outer_params
    ).fetchone()[0]

    if sort_by == 'left_budget':
        order_clause = f"CASE WHEN left_budget IS NULL THEN 1 ELSE 0 END, left_budget {sort_order}, id DESC"
    else:
        order_clause = f"{sort_by} {sort_order}, id DESC"

    rows = db.execute(
        f"""
        WITH base AS (
            SELECT r.id, r.category, r.amount, r.note, r.date,
                   r.anomaly_score, r.anomaly_flag,
                   strftime('%Y-%m', r.date) as month,
                   SUM(r.amount) OVER (
                       PARTITION BY r.user_id, r.category, strftime('%Y-%m', r.date)
                       ORDER BY r.date, r.id
                       ROWS UNBOUNDED PRECEDING
                   ) as cumulative_spend
            FROM records r WHERE r.user_id = ?
        ),
        enriched AS (
            SELECT base.id, base.category, base.amount, base.note, base.date, base.month,
                   base.anomaly_score, base.anomaly_flag,
                   CASE WHEN b.amount IS NOT NULL
                        THEN ROUND(b.amount - base.cumulative_spend, 2)
                        ELSE NULL END as left_budget
            FROM base
            LEFT JOIN budgets b ON b.user_id = ? AND b.category = base.category AND b.month = base.month
        )
        SELECT * FROM enriched {outer_where}
        ORDER BY {order_clause} LIMIT ? OFFSET ?
        """,
        [g.user_id, g.user_id] + outer_params + [limit, offset]
    ).fetchall()

    results = []
    for row in rows:
        r = dict(row)
        lb = r['left_budget']
        r['left_budget'] = f"{lb:.2f}" if lb is not None else '—'
        results.append(r)

    return jsonify({"data": results, "total": total, "page": page, "limit": limit})


@records_bp.route('/api/records', methods=['POST'])
@login_required
def create_record():
    """直接创建记录。支持 auto_categorize=true：当未提供 category 且有备注时，
    查缓存 / 调 LLM 自动归类；命中即写库，未命中返回 needs_category。"""
    data = request.get_json() or {}
    category = (data.get("category") or "").strip()
    note = (data.get("note") or "").strip()
    try:
        amount = float(data.get("amount") or 0)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "amount 必须为数字"}), 400
    if amount <= 0:
        return jsonify({"success": False, "error": "amount 必须大于 0"}), 400
    date = (data.get("date") or "").strip()

    auto = bool(data.get("auto_categorize")) and not category
    cat_source = None
    if auto:
        if not note:
            return jsonify({
                "success": False,
                "needs_category": True,
                "error": "自动归类需要填写备注",
            }), 400
        from services.categorizer import categorize
        pick = categorize(g.user_id, note, llm=_load_llm_cfg())
        category = pick["category"]
        cat_source = pick["source"]
        if not category:
            return jsonify({
                "success": False,
                "needs_category": True,
                "error": "无法自动归类，请手动选择分类",
            }), 200

    if not category:
        return jsonify({"success": False, "error": "分类不能为空"}), 400

    from handlers import add_record
    msg = add_record(g.user_id, {
        PARAM_CATEGORY: category,
        PARAM_AMOUNT: amount,
        PARAM_NOTE: note,
        PARAM_DATE: date,
    })
    success = msg.startswith("✅")
    payload = {"success": success, "message": msg, "category": category}
    if cat_source:
        payload["category_source"] = cat_source
    return jsonify(payload), (200 if success else 400)


@records_bp.route('/api/records/<int:record_id>', methods=['DELETE'])
@login_required
def delete_record(record_id):
    db = get_db()
    row = db.execute(
        "SELECT category FROM records WHERE id = ? AND user_id = ?",
        (record_id, g.user_id),
    ).fetchone()
    db.execute(
        "DELETE FROM records WHERE id = ? AND user_id = ?",
        (record_id, g.user_id)
    )
    db.commit()
    if row:
        cleanup_empty_category(g.user_id, row["category"])
    invalidate_user(g.user_id)
    return jsonify({"success": True})


@records_bp.route('/api/records/<int:record_id>', methods=['PUT'])
@login_required
def update_record(record_id):
    data = request.get_json()
    category = data.get('category', '').strip()
    amount = float(data.get('amount', 0))
    note = data.get('note', '').strip()
    date = data.get('date')
    db = get_db()
    old_row = db.execute(
        "SELECT category FROM records WHERE id = ? AND user_id = ?",
        (record_id, g.user_id),
    ).fetchone()
    db.execute(
        "UPDATE records SET category = ?, amount = ?, note = ?, date = ? WHERE id = ? AND user_id = ?",
        (category, amount, note, date, record_id, g.user_id),
    )
    db.commit()
    if old_row and old_row["category"] != category:
        cleanup_empty_category(g.user_id, old_row["category"])
    invalidate_user(g.user_id)
    return jsonify({"success": True})
