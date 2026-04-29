"""月度报告生成：聚合数据 → LLM 写 Markdown → 持久化到 reports 表。

异步设计：LLM 写 7 个章节 + 表格的 Markdown 经常 > 60s，同步会被 nginx /
Waitress / 前端 timeout 砍掉。改为：
  * POST 立即在 reports 表写 status='pending' 行 + 启动后台线程
  * 后台线程切 status='running' → 调 LLM → 写 content + status='done'
  * 失败写 status='failed' + error_message
  * 前端轮询 GET /api/reports/<period>/status
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

from db import get_db, DB_FILE

logger = logging.getLogger(__name__)

# 单 worker 串行：避免一个用户连点 N 次重复跑 LLM；多个用户并发由 ThreadPool
# 自动排队。LLM 本身有每用户每日 token 配额做兜底。
_REPORT_EXECUTOR = ThreadPoolExecutor(
    max_workers=int(os.getenv("REPORT_WORKERS", "2")),
    thread_name_prefix="report-gen",
)
_inflight: dict[tuple[int, str], threading.Event] = {}
_inflight_lock = threading.Lock()


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
    """启动异步生成。立即返回 {period, status: 'pending'|'running'|'done', ...}。

    历史路径调用方仍可拿到 content（当无 LLM 调用时直接返回静态内容）；
    需要走 LLM 的场景会立即返回 pending，前端通过 status 端点轮询。
    """
    if not period:
        period = datetime.now().strftime("%Y-%m")

    insights = _aggregate(user_id, period)
    has_activity = bool(insights["by_category_spend"] or insights["by_category_income"])
    has_portfolio = bool(insights.get("portfolio", {}).get("has_portfolio"))
    now = datetime.now().isoformat(timespec="seconds")

    if not has_activity and not has_portfolio:
        # 无数据时直接落库为 done，跳过 LLM
        empty_content = f"# {period} 月度报告\n\n📭 该月无任何记录，无需生成报告。"
        _upsert_report(user_id, period, empty_content, insights, status="done", now=now)
        return {
            "period": period,
            "status": "done",
            "content": empty_content,
            "insights": insights,
            "created_at": now,
            "stored": True,
        }

    # 已有 running/pending 任务则不重复启动
    key = (user_id, period)
    with _inflight_lock:
        if key in _inflight:
            return {
                "period": period,
                "status": "running",
                "message": "已有报告生成任务在跑，请稍候并轮询 status 端点",
            }
        _inflight[key] = threading.Event()

    # 占位行：让前端立即能看到 status=pending
    _upsert_report(user_id, period, content=None, insights=insights,
                   status="pending", now=now)

    _REPORT_EXECUTOR.submit(_run_async, user_id, period, insights, llm)

    return {
        "period": period,
        "status": "pending",
        "message": "报告生成已开始，请轮询 status 端点（一般 1-3 分钟内完成）",
        "created_at": now,
    }


def _run_async(user_id: int, period: str, insights: dict, llm: Optional[dict]) -> None:
    """后台线程入口：独立 sqlite 连接，避免与 Flask 请求线程的 g.db 冲突。"""
    key = (user_id, period)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        # 切到 running，给前端"已经在跑"信号
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            "UPDATE reports SET status = 'running', updated_at = ? "
            "WHERE user_id = ? AND period = ?",
            (now, user_id, period),
        )
        conn.commit()

        from services.llm import call_llm_monthly_report
        content = call_llm_monthly_report(insights, llm=llm)
        # 简单失败检测：LLM 返回的"⚠️ 生成失败"开头视为 failed
        if isinstance(content, str) and content.lstrip().startswith("⚠️"):
            raise RuntimeError(content[:200])

        finished = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            """
            UPDATE reports SET
                content = ?,
                insights_json = ?,
                status = 'done',
                error_message = NULL,
                created_at = ?,
                updated_at = ?
            WHERE user_id = ? AND period = ?
            """,
            (content, json.dumps(insights, ensure_ascii=False), finished, finished,
             user_id, period),
        )
        conn.commit()
        logger.info("monthly_report done user=%s period=%s", user_id, period)
    except Exception as e:  # noqa: BLE001
        logger.exception("monthly_report failed user=%s period=%s", user_id, period)
        try:
            conn.execute(
                "UPDATE reports SET status = 'failed', error_message = ?, "
                "updated_at = ? WHERE user_id = ? AND period = ?",
                (str(e)[:500], datetime.now().isoformat(timespec="seconds"),
                 user_id, period),
            )
            conn.commit()
        except sqlite3.Error:
            pass
    finally:
        conn.close()
        with _inflight_lock:
            ev = _inflight.pop(key, None)
        if ev is not None:
            ev.set()


def _upsert_report(user_id: int, period: str, content: Optional[str],
                   insights: dict, *, status: str, now: str) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO reports (user_id, period, format, content, insights_json,
                             status, error_message, created_at, updated_at)
        VALUES (?, ?, 'markdown', ?, ?, ?, NULL, ?, ?)
        ON CONFLICT(user_id, period) DO UPDATE SET
            content = COALESCE(excluded.content, reports.content),
            insights_json = excluded.insights_json,
            status = excluded.status,
            error_message = NULL,
            updated_at = excluded.updated_at
        """,
        (user_id, period, content, json.dumps(insights, ensure_ascii=False),
         status, now, now),
    )
    db.commit()


def get_report_status(user_id: int, period: str) -> dict | None:
    """轻量查询：仅返回状态字段，不带 content/insights，避免轮询时反复传大体积。"""
    row = get_db().execute(
        "SELECT period, status, error_message, created_at, updated_at "
        "FROM reports WHERE user_id = ? AND period = ?",
        (user_id, period),
    ).fetchone()
    if not row:
        return None
    return dict(row)


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
