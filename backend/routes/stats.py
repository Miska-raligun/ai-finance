"""统计数据路由"""
import re
from datetime import datetime
from flask import Blueprint, request, jsonify, g, abort
from db import get_db
from auth import login_required
from constants import CATEGORY_EXPENSE, CATEGORY_INCOME
from cache import make_key, get_or_compute

stats_bp = Blueprint('stats', __name__)

# 消费/日历/异常/预算等「消费分析」视图排除投资盈亏结算(卖出/归档写入的
# source='investment' 行);而 summary 的总收支 / 结余仍计入,保留其对净现金流
# 的影响(方案 A:不污染消费结构,但影响总收支)。
NOT_INVESTMENT = "AND (source IS NULL OR source != 'investment')"

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


@stats_bp.route("/api/stats/today", methods=["GET"])
@login_required
def today_stats():
    """首页速览：今天已花 / 本月已花 / 本月预算总额与剩余。

    专为 HomeView 设计的单端点——打开首页只发一个请求就能渲染速览条,
    避免首页也要像 LedgerView 那样并发拉 3 个接口。"""
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    month = today[:7]

    today_spend = float(db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM records "
        "WHERE user_id = ? AND date = ? AND deleted_at IS NULL",
        (g.user_id, today),
    ).fetchone()[0])
    month_spend = float(db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM records "
        "WHERE user_id = ? AND strftime('%Y-%m', date) = ? AND deleted_at IS NULL",
        (g.user_id, month),
    ).fetchone()[0])
    budget_total = float(db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM budgets WHERE user_id = ? AND month = ?",
        (g.user_id, month),
    ).fetchone()[0])

    return jsonify({
        "date": today,
        "month": month,
        "today_spend": round(today_spend, 2),
        "month_spend": round(month_spend, 2),
        "budget_total": round(budget_total, 2),
        # 没设预算时返回 null,前端据此隐藏"预算剩余"而不是显示负数
        "budget_remaining": round(budget_total - month_spend, 2) if budget_total > 0 else None,
    })


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
               FROM records WHERE user_id=? AND strftime('%Y',date) IN (?,?)
                 AND deleted_at IS NULL""",
            (year, prev_year, g.user_id, year, prev_year),
        ).fetchone()
        income_row = db.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN strftime('%Y',date)=? THEN amount END), 0) as cur,
                 COALESCE(SUM(CASE WHEN strftime('%Y',date)=? THEN amount END), 0) as prev
               FROM income WHERE user_id=? AND strftime('%Y',date) IN (?,?)
                 AND deleted_at IS NULL""",
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
               FROM records WHERE user_id=? AND strftime('%Y-%m',date) IN (?,?)
                 AND deleted_at IS NULL""",
            (month, prev_month, g.user_id, month, prev_month),
        ).fetchone()
        income_row = db.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN strftime('%Y-%m',date)=? THEN amount END), 0) as cur,
                 COALESCE(SUM(CASE WHEN strftime('%Y-%m',date)=? THEN amount END), 0) as prev
               FROM income WHERE user_id=? AND strftime('%Y-%m',date) IN (?,?)
                 AND deleted_at IS NULL""",
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
              AND deleted_at IS NULL
            GROUP BY month
            """,
            (year, g.user_id),
        )
        income_cursor = db.execute(
            """
            SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total
            FROM income WHERE strftime('%Y', date) = ? AND user_id = ?
              AND deleted_at IS NULL
            GROUP BY month
            """,
            (year, g.user_id),
        )
    else:
        spend_cursor = db.execute(
            """
            SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total
            FROM records
            WHERE user_id = ? AND deleted_at IS NULL
            GROUP BY month
            """,
            (g.user_id,)
        )
        income_cursor = db.execute(
            """
            SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total
            FROM income
            WHERE user_id = ? AND deleted_at IS NULL
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
        "FROM records WHERE user_id = ? AND deleted_at IS NULL GROUP BY year",
        (g.user_id,)
    )
    income_cursor = db.execute(
        "SELECT strftime('%Y', date) AS year, SUM(amount) AS total "
        "FROM income WHERE user_id = ? AND deleted_at IS NULL GROUP BY year",
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
    # 消费/收入结构分析排除投资盈亏(source='investment'),避免"投资亏损"当消费、
    # "投资盈利"当收入污染分类饼图。总收支仍在 summary 里计入。
    db = get_db()
    NI = NOT_INVESTMENT
    if month:
        spend_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM records "
            f"WHERE strftime('%Y-%m', date) = ? AND user_id = ? AND deleted_at IS NULL {NI} GROUP BY category",
            (month, g.user_id),
        )
        income_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM income "
            f"WHERE strftime('%Y-%m', date) = ? AND user_id = ? AND deleted_at IS NULL {NI} GROUP BY category",
            (month, g.user_id),
        )
    elif year:
        spend_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM records "
            f"WHERE strftime('%Y', date) = ? AND user_id = ? AND deleted_at IS NULL {NI} GROUP BY category",
            (year, g.user_id),
        )
        income_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM income "
            f"WHERE strftime('%Y', date) = ? AND user_id = ? AND deleted_at IS NULL {NI} GROUP BY category",
            (year, g.user_id),
        )
    else:
        spend_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM records "
            f"WHERE user_id = ? AND deleted_at IS NULL {NI} GROUP BY category",
            (g.user_id,)
        )
        income_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM income "
            f"WHERE user_id = ? AND deleted_at IS NULL {NI} GROUP BY category",
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
          AND deleted_at IS NULL
    """,
        (month, g.user_id)
    )
    spend_total = float(spend_cursor.fetchone()["total"] or 0.0)

    income_cursor = db.execute(
        """
        SELECT SUM(amount) AS total
        FROM income
        WHERE strftime('%Y-%m', date) = ? AND user_id = ?
          AND deleted_at IS NULL
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
          AND deleted_at IS NULL AND (source IS NULL OR source != 'investment')
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
          AND deleted_at IS NULL AND (source IS NULL OR source != 'investment')
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


@stats_bp.route("/api/stats/calendar")
@login_required
def calendar_stats():
    """日历热力图数据：过去 N 天每天的支出/收入。

    Query: days = 90 | 180 | 365 (clamp 30..730)
    返回 [{date, expense, income}]，按日期升序。
    """
    try:
        days = int(request.args.get("days", 90))
    except (TypeError, ValueError):
        days = 90
    days = max(30, min(730, days))

    db = get_db()
    spend_rows = db.execute(
        "SELECT date, SUM(amount) AS total FROM records "
        "WHERE user_id = ? AND date >= date('now', ?) "
        "AND deleted_at IS NULL AND (source IS NULL OR source != 'investment') "
        "GROUP BY date",
        (g.user_id, f"-{days} days"),
    ).fetchall()
    income_rows = db.execute(
        "SELECT date, SUM(amount) AS total FROM income "
        "WHERE user_id = ? AND date >= date('now', ?) "
        "AND deleted_at IS NULL AND (source IS NULL OR source != 'investment') "
        "GROUP BY date",
        (g.user_id, f"-{days} days"),
    ).fetchall()
    spend = {r["date"]: float(r["total"]) for r in spend_rows}
    income = {r["date"]: float(r["total"]) for r in income_rows}
    all_dates = sorted(set(spend) | set(income))
    return jsonify({
        "days": days,
        "data": [
            {"date": d,
             "expense": round(spend.get(d, 0.0), 2),
             "income": round(income.get(d, 0.0), 2)}
            for d in all_dates
        ],
    })
