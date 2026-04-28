"""统计数据路由"""
import re
from datetime import datetime
from flask import Blueprint, request, jsonify, g, abort
from db import get_db
from auth import login_required
from constants import CATEGORY_EXPENSE, CATEGORY_INCOME
from cache import make_key, get_or_compute

stats_bp = Blueprint('stats', __name__)

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_YEAR_RE = re.compile(r"^\d{4}$")


def _validate_month(value: str | None, *, required: bool = False) -> str | None:
    """规范化 YYYY-MM 参数。无效输入直接 400，避免后续 int(month[:4]) 在异常输入上崩。"""
    if not value:
        if required:
            abort(400, description="缺少参数 month")
        return None
    v = value.strip()
    if not _MONTH_RE.match(v):
        abort(400, description=f"month 参数格式应为 YYYY-MM：{value!r}")
    yr = int(v[:4])
    if yr < 1970 or yr > 2999:
        abort(400, description=f"month 年份越界：{value!r}")
    return v


def _validate_year(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()
    if not _YEAR_RE.match(v):
        abort(400, description=f"year 参数格式应为 YYYY：{value!r}")
    yr = int(v)
    if yr < 1970 or yr > 2999:
        abort(400, description=f"year 越界：{value!r}")
    return v


@stats_bp.route("/api/stats/comparison", methods=["GET"])
@login_required
def comparison_stats():
    """月度环比 / 年度同比对比（优化：2 条 SQL）"""
    db = get_db()
    month = _validate_month(request.args.get("month"))
    year = _validate_year(request.args.get("year"))

    if year:
        # 年度同比
        prev_year = str(int(year) - 1)
        expense_row = db.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN strftime('%Y',date)=? THEN amount END), 0) as cur,
                 COALESCE(SUM(CASE WHEN strftime('%Y',date)=? THEN amount END), 0) as prev
               FROM records WHERE user_id=? AND strftime('%Y',date) IN (?,?)""",
            (year, prev_year, g.user_id, year, prev_year),
        ).fetchone()
        income_row = db.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN strftime('%Y',date)=? THEN amount END), 0) as cur,
                 COALESCE(SUM(CASE WHEN strftime('%Y',date)=? THEN amount END), 0) as prev
               FROM income WHERE user_id=? AND strftime('%Y',date) IN (?,?)""",
            (year, prev_year, g.user_id, year, prev_year),
        ).fetchone()
    else:
        # 月度环比
        month = month or datetime.now().strftime("%Y-%m")
        yr, mon = int(month[:4]), int(month[5:7])
        prev_month = f"{yr - 1}-12" if mon == 1 else f"{yr}-{mon - 1:02d}"
        expense_row = db.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN strftime('%Y-%m',date)=? THEN amount END), 0) as cur,
                 COALESCE(SUM(CASE WHEN strftime('%Y-%m',date)=? THEN amount END), 0) as prev
               FROM records WHERE user_id=? AND strftime('%Y-%m',date) IN (?,?)""",
            (month, prev_month, g.user_id, month, prev_month),
        ).fetchone()
        income_row = db.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN strftime('%Y-%m',date)=? THEN amount END), 0) as cur,
                 COALESCE(SUM(CASE WHEN strftime('%Y-%m',date)=? THEN amount END), 0) as prev
               FROM income WHERE user_id=? AND strftime('%Y-%m',date) IN (?,?)""",
            (month, prev_month, g.user_id, month, prev_month),
        ).fetchone()

    cur_expense, prev_expense = float(expense_row["cur"]), float(expense_row["prev"])
    cur_income, prev_income = float(income_row["cur"]), float(income_row["prev"])
    cur_balance = cur_income - cur_expense
    prev_balance = prev_income - prev_expense

    def _calc_change(cur, prev):
        change = cur - prev
        pct = (change / prev * 100) if prev > 0 else (100 if cur > 0 else 0)
        return {
            "current": round(cur, 2), "previous": round(prev, 2),
            "change": round(change, 2), "change_pct": round(pct, 1),
        }

    return jsonify({
        "expense": _calc_change(cur_expense, prev_expense),
        "income": _calc_change(cur_income, prev_income),
        "balance": _calc_change(cur_balance, prev_balance),
    })


@stats_bp.route("/api/stats/monthly", methods=["GET"])
@login_required
def monthly_stats():
    year = _validate_year(request.args.get("year"))
    cache_key = make_key(g.user_id, "monthly", year=year or "all")
    return jsonify(get_or_compute(cache_key, lambda: _monthly_stats_compute(year)))


def _monthly_stats_compute(year):
    db = get_db()
    if year:
        spend_cursor = db.execute(
            """
            SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total
            FROM records WHERE strftime('%Y', date) = ? AND user_id = ?
            GROUP BY month
            """,
            (year, g.user_id),
        )
        income_cursor = db.execute(
            """
            SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total
            FROM income WHERE strftime('%Y', date) = ? AND user_id = ?
            GROUP BY month
            """,
            (year, g.user_id),
        )
    else:
        spend_cursor = db.execute(
            """
            SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total
            FROM records
            WHERE user_id = ?
            GROUP BY month
            """,
            (g.user_id,)
        )
        income_cursor = db.execute(
            """
            SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total
            FROM income
            WHERE user_id = ?
            GROUP BY month
            """,
            (g.user_id,)
        )

    spend_data = {row['month']: float(row['total']) for row in spend_cursor.fetchall()}
    income_data = {row['month']: float(row['total']) for row in income_cursor.fetchall()}

    if year:
        months = [f"{year}-{i:02d}" for i in range(1, 13)]
    else:
        months = sorted(set(spend_data.keys()) | set(income_data.keys()))

    result = []
    for m in months:
        result.append({
            "month": m,
            CATEGORY_EXPENSE: spend_data.get(m, 0.0),
            CATEGORY_INCOME: income_data.get(m, 0.0)
        })

    return result


@stats_bp.route("/api/stats/yearly", methods=["GET"])
@login_required
def yearly_stats():
    db = get_db()
    spend_cursor = db.execute(
        "SELECT strftime('%Y', date) AS year, SUM(amount) AS total "
        "FROM records WHERE user_id = ? GROUP BY year",
        (g.user_id,)
    )
    income_cursor = db.execute(
        "SELECT strftime('%Y', date) AS year, SUM(amount) AS total "
        "FROM income WHERE user_id = ? GROUP BY year",
        (g.user_id,)
    )
    spend_data = {row['year']: float(row['total']) for row in spend_cursor.fetchall()}
    income_data = {row['year']: float(row['total']) for row in income_cursor.fetchall()}
    years = sorted(set(spend_data.keys()) | set(income_data.keys()))
    return jsonify([
        {"year": y, CATEGORY_INCOME: income_data.get(y, 0.0), CATEGORY_EXPENSE: spend_data.get(y, 0.0)}
        for y in years
    ])


@stats_bp.route("/api/stats/by-category", methods=["GET"])
@login_required
def category_stats():
    month = _validate_month(request.args.get("month"))
    year = _validate_year(request.args.get("year"))
    cache_key = make_key(g.user_id, "by_category", month=month, year=year)
    return jsonify(get_or_compute(cache_key, lambda: _category_stats_compute(month, year)))


def _category_stats_compute(month, year):
    db = get_db()
    if month:
        spend_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM records WHERE strftime('%Y-%m', date) = ? AND user_id = ? GROUP BY category",
            (month, g.user_id),
        )
        income_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM income WHERE strftime('%Y-%m', date) = ? AND user_id = ? GROUP BY category",
            (month, g.user_id),
        )
    elif year:
        spend_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM records WHERE strftime('%Y', date) = ? AND user_id = ? GROUP BY category",
            (year, g.user_id),
        )
        income_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM income WHERE strftime('%Y', date) = ? AND user_id = ? GROUP BY category",
            (year, g.user_id),
        )
    else:
        spend_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM records WHERE user_id = ? GROUP BY category",
            (g.user_id,)
        )
        income_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM income WHERE user_id = ? GROUP BY category",
            (g.user_id,)
        )

    income_result = [
        {"名称": row["name"], "金额": float(row["total"]), "类型": CATEGORY_INCOME}
        for row in income_cursor.fetchall()
    ]
    spend_result = [
        {"名称": row["name"], "金额": float(row["total"]), "类型": CATEGORY_EXPENSE}
        for row in spend_cursor.fetchall()
    ]
    return spend_result + income_result


@stats_bp.route("/api/stats/summary", methods=["GET"])
@login_required
def summary_stats():
    db = get_db()
    month = _validate_month(request.args.get("month")) or datetime.now().strftime("%Y-%m")

    spend_cursor = db.execute(
        """
        SELECT SUM(amount) AS total
        FROM records
        WHERE strftime('%Y-%m', date) = ? AND user_id = ?
    """,
        (month, g.user_id)
    )
    spend_total = float(spend_cursor.fetchone()["total"] or 0.0)

    income_cursor = db.execute(
        """
        SELECT SUM(amount) AS total
        FROM income
        WHERE strftime('%Y-%m', date) = ? AND user_id = ?
    """,
        (month, g.user_id)
    )
    income_total = float(income_cursor.fetchone()["total"] or 0.0)

    balance = income_total - spend_total

    return jsonify({
        "month": month,
        "总支出": round(spend_total, 2),
        "总收入": round(income_total, 2),
        "结余": round(balance, 2)
    })


@stats_bp.route("/api/stats/daily")
@login_required
def daily_stats():
    month = _validate_month(request.args.get("month"), required=True)
    cache_key = make_key(g.user_id, "daily", month=month)
    return jsonify(get_or_compute(cache_key, lambda: _daily_stats_compute(month)))


def _daily_stats_compute(month):
    db = get_db()
    spend_cursor = db.execute(
        """
        SELECT date, SUM(amount) AS total
        FROM records
        WHERE strftime('%Y-%m', date) = ? AND user_id = ?
        GROUP BY date
    """,
        (month, g.user_id)
    )
    spend_map = {row['date']: float(row['total']) for row in spend_cursor.fetchall()}

    income_cursor = db.execute(
        """
        SELECT date, SUM(amount) AS total
        FROM income
        WHERE strftime('%Y-%m', date) = ? AND user_id = ?
        GROUP BY date
    """,
        (month, g.user_id)
    )
    income_map = {row['date']: float(row['total']) for row in income_cursor.fetchall()}

    all_dates = sorted(set(spend_map) | set(income_map))
    result = []
    for d in all_dates:
        spend = spend_map.get(d, 0.0)
        income = income_map.get(d, 0.0)
        result.append({
            "date": d,
            CATEGORY_EXPENSE: spend,
            CATEGORY_INCOME: income,
            "结余": round(income - spend, 2)
        })

    return result
