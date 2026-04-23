"""月度报告生成：聚合数据 → LLM 写 Markdown → 持久化到 reports 表。"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from db import get_db

logger = logging.getLogger(__name__)


def _aggregate(user_id: int, period: str) -> dict:
    db = get_db()
    spend = [dict(r) for r in db.execute(
        "SELECT category, SUM(amount) AS total, COUNT(*) AS cnt "
        "FROM records WHERE user_id = ? AND strftime('%Y-%m', date) = ? "
        "GROUP BY category ORDER BY total DESC",
        (user_id, period),
    ).fetchall()]
    income = [dict(r) for r in db.execute(
        "SELECT category, SUM(amount) AS total FROM income "
        "WHERE user_id = ? AND strftime('%Y-%m', date) = ? GROUP BY category ORDER BY total DESC",
        (user_id, period),
    ).fetchall()]
    budgets = [dict(r) for r in db.execute(
        "SELECT category, amount FROM budgets WHERE user_id = ? AND month = ?",
        (user_id, period),
    ).fetchall()]
    anomalies = [dict(r) for r in db.execute(
        "SELECT date, category, amount, note, anomaly_score FROM records "
        "WHERE user_id = ? AND strftime('%Y-%m', date) = ? AND anomaly_flag = 1 "
        "ORDER BY date DESC LIMIT 10",
        (user_id, period),
    ).fetchall()]

    spend_total = sum(r["total"] for r in spend)
    income_total = sum(r["total"] for r in income)
    return {
        "period": period,
        "spend_total": round(spend_total, 2),
        "income_total": round(income_total, 2),
        "net": round(income_total - spend_total, 2),
        "by_category_spend": spend,
        "by_category_income": income,
        "budgets": budgets,
        "anomalies": anomalies,
        "portfolio": _aggregate_portfolio(user_id),
    }


def _aggregate_portfolio(user_id: int) -> dict:
    """投资组合快照（报告生成时刻）：总市值 / 盈亏 / 类型分布 / 前 5 持仓 / 目标进度。"""
    from services.portfolio import (
        build_holding_details, compute_allocation, compute_return,
    )
    db = get_db()
    asset_rows = db.execute(
        "SELECT name, type, symbol, holdings, cost_basis, current_value "
        "FROM assets WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    assets = [dict(r) for r in asset_rows]
    has_portfolio = bool(assets)

    goal_rows = db.execute(
        "SELECT name, target_amount, current_progress, deadline, priority "
        "FROM financial_goals WHERE user_id = ? ORDER BY priority ASC, deadline ASC",
        (user_id,),
    ).fetchall()
    goals = []
    for r in goal_rows:
        target = float(r["target_amount"] or 0)
        done = float(r["current_progress"] or 0)
        goals.append({
            "name": r["name"],
            "target_amount": round(target, 2),
            "current_progress": round(done, 2),
            "progress_pct": round((done / target * 100) if target > 0 else 0.0, 2),
            "deadline": r["deadline"],
            "priority": r["priority"],
        })

    if not has_portfolio:
        return {"has_portfolio": False, "goals": goals}

    allocation = compute_allocation(assets)
    returns = compute_return(assets)
    holdings = build_holding_details(assets)
    return {
        "has_portfolio": True,
        "total_value": returns["total_value"],
        "total_cost": returns["total_cost"],
        "pnl": returns["pnl"],
        "return_pct": returns["return_pct"],
        "by_type": allocation.get("by_type", []),
        "top_holdings": holdings[:5],
        "goals": goals,
    }


def generate_monthly_report(user_id: int, period: Optional[str] = None,
                            llm: Optional[dict] = None) -> dict:
    """生成（或覆盖）某月报告。返回 {period, content, insights, created_at}。"""
    if not period:
        period = datetime.now().strftime("%Y-%m")

    insights = _aggregate(user_id, period)
    has_activity = bool(insights["by_category_spend"] or insights["by_category_income"])
    has_portfolio = bool(insights.get("portfolio", {}).get("has_portfolio"))
    if not has_activity and not has_portfolio:
        return {
            "period": period,
            "content": f"# {period} 月度报告\n\n📭 该月无任何记录，无需生成报告。",
            "insights": insights,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "stored": False,
        }

    from services.llm import call_llm_monthly_report
    content = call_llm_monthly_report(insights, llm=llm)

    now = datetime.now().isoformat(timespec="seconds")
    db = get_db()
    db.execute(
        """
        INSERT INTO reports (user_id, period, format, content, insights_json, created_at)
        VALUES (?, ?, 'markdown', ?, ?, ?)
        ON CONFLICT(user_id, period) DO UPDATE SET
            content = excluded.content,
            insights_json = excluded.insights_json,
            created_at = excluded.created_at
        """,
        (user_id, period, content, json.dumps(insights, ensure_ascii=False), now),
    )
    db.commit()

    return {
        "period": period,
        "content": content,
        "insights": insights,
        "created_at": now,
        "stored": True,
    }


def list_reports(user_id: int) -> list[dict]:
    rows = get_db().execute(
        "SELECT period, created_at FROM reports WHERE user_id = ? ORDER BY period DESC",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_report(user_id: int, period: str) -> dict | None:
    row = get_db().execute(
        "SELECT period, content, insights_json, created_at FROM reports "
        "WHERE user_id = ? AND period = ?",
        (user_id, period),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    if d.get("insights_json"):
        try:
            d["insights"] = json.loads(d["insights_json"])
        except json.JSONDecodeError:
            d["insights"] = None
    d.pop("insights_json", None)
    return d
