"""财务分析报告：合并 4 次 SQL 为 2 次的版本。"""
from __future__ import annotations

from typing import Any

from constants import PARAM_MONTH
from db import get_db

from ._common import cur_month, prev_month_of


def analyze_spend(user_id: int, params: dict[str, Any]) -> str:
    """财务分析报告 — 使用合并查询优化（4→2 次数据库往返）。"""
    db = get_db()
    month = params.get(PARAM_MONTH) or cur_month()

    reply = f"📊「{month}」财务分析报告：\n"

    # 一次性算出每个分类的"总体"和"本月"两个值
    spend_rows = db.execute(
        """
        SELECT category,
               SUM(amount) as overall_total,
               SUM(CASE WHEN strftime('%Y-%m', date) = ? THEN amount ELSE 0 END) as monthly_total
        FROM records WHERE user_id = ?
        GROUP BY category
        ORDER BY overall_total DESC
        LIMIT 10
        """,
        (month, user_id)
    ).fetchall()

    income_rows = db.execute(
        """
        SELECT category,
               SUM(amount) as overall_total,
               SUM(CASE WHEN strftime('%Y-%m', date) = ? THEN amount ELSE 0 END) as monthly_total
        FROM income WHERE user_id = ?
        GROUP BY category
        ORDER BY overall_total DESC
        LIMIT 10
        """,
        (month, user_id)
    ).fetchall()

    # === 支出分析输出 ===
    monthly_spend = [(r['category'], r['monthly_total']) for r in spend_rows if r['monthly_total'] > 0]
    monthly_spend.sort(key=lambda x: x[1], reverse=True)
    overall_spend = [(r['category'], r['overall_total']) for r in spend_rows if r['overall_total'] > 0]

    reply += "\n💸 本月支出排行：\n"
    if monthly_spend:
        for cat, total in monthly_spend[:5]:
            reply += f"👉 分类「{cat}」共支出 ¥{total:.2f}\n"
    else:
        reply += "暂无支出记录。\n"

    reply += "\n📌 总体支出排行：\n"
    if overall_spend:
        for cat, total in overall_spend[:5]:
            reply += f"📌 分类「{cat}」累计支出 ¥{total:.2f}\n"
    else:
        reply += "暂无历史支出数据。\n"

    # === 收入分析输出 ===
    monthly_income = [(r['category'], r['monthly_total']) for r in income_rows if r['monthly_total'] > 0]
    monthly_income.sort(key=lambda x: x[1], reverse=True)
    overall_income = [(r['category'], r['overall_total']) for r in income_rows if r['overall_total'] > 0]

    reply += "\n💰 本月收入来源排行：\n"
    if monthly_income:
        for cat, total in monthly_income[:5]:
            reply += f"✅ 来源「{cat}」共收入 ¥{total:.2f}\n"
    else:
        reply += "暂无收入记录。\n"

    reply += "\n📈 总体收入来源排行：\n"
    if overall_income:
        for cat, total in overall_income[:5]:
            reply += f"📈 来源「{cat}」累计收入 ¥{total:.2f}\n"
    else:
        reply += "暂无历史收入数据。\n"

    # ── 环比上月对比 ──
    prev_month = prev_month_of(month)

    prev_spend = float(db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM records WHERE strftime('%Y-%m', date) = ? AND user_id = ?",
        (prev_month, user_id),
    ).fetchone()[0])
    prev_income = float(db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM income WHERE strftime('%Y-%m', date) = ? AND user_id = ?",
        (prev_month, user_id),
    ).fetchone()[0])

    cur_spend = sum(r["monthly_total"] for r in spend_rows)
    cur_income_total = sum(r["monthly_total"] for r in income_rows)

    def _arrow(cur: float, prev: float) -> str:
        if prev == 0:
            return "（上月无数据）"
        pct = (cur - prev) / prev * 100
        arrow = "↑" if pct > 0 else "↓"
        return f"{arrow} {abs(pct):.1f}%（上月 ¥{prev:.2f}）"

    reply += f"\n📊 **环比上月（{prev_month}）**\n"
    reply += f"  支出：¥{cur_spend:.2f} {_arrow(cur_spend, prev_spend)}\n"
    reply += f"  收入：¥{cur_income_total:.2f} {_arrow(cur_income_total, prev_income)}\n"

    reply += "\n📌 建议：保持合理收支平衡，做好财务规划 👍"
    return reply
