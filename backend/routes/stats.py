"""统计数据路由"""
from datetime import datetime
from flask import Blueprint, request, jsonify, g
from db import get_db
from auth import login_required
from constants import CATEGORY_EXPENSE, CATEGORY_INCOME

stats_bp = Blueprint('stats', __name__)


@stats_bp.route("/api/stats/monthly", methods=["GET"])
@login_required
def monthly_stats():
    db = get_db()
    year = request.args.get("year")
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

    return jsonify(result)


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
    db = get_db()
    month = request.args.get("month")
    year = request.args.get("year")

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
    return jsonify(spend_result + income_result)


@stats_bp.route("/api/stats/summary", methods=["GET"])
@login_required
def summary_stats():
    db = get_db()
    month = request.args.get("month") or datetime.now().strftime("%Y-%m")

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
    db = get_db()
    month = request.args.get("month")
    if not month:
        return jsonify({"error": "缺少参数 month"}), 400

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

    return jsonify(result)
