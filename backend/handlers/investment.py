"""投资模块 LLM 工具入口（中文键参数）。"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from typing import Any

from cache import invalidate_user
from db import get_db

logger = logging.getLogger(__name__)


def _resolve_asset_type(user_id: int, atype: str) -> dict | None:
    """查询当前用户已登记的资产类型定义。"""
    row = get_db().execute(
        "SELECT name, shape, quote_source FROM asset_types "
        "WHERE user_id = ? AND name = ?",
        (user_id, atype),
    ).fetchone()
    return dict(row) if row else None


def invest_add_asset(user_id: int, params: dict[str, Any]) -> str:
    name = (params.get("名称") or "").strip()
    atype = (params.get("类型") or "").strip()
    if not name:
        return "⚠️ 请提供资产名称"
    if not atype:
        return "⚠️ 请提供资产类型"
    type_def = _resolve_asset_type(user_id, atype)
    if not type_def:
        available = [r["name"] for r in get_db().execute(
            "SELECT name FROM asset_types WHERE user_id = ? ORDER BY id", (user_id,),
        ).fetchall()]
        hint = "，你可创建的类型有：" + "、".join(available) if available else ""
        return f"⚠️ 资产类型「{atype}」未定义，请先在投资页的「类型管理」中创建{hint}"
    try:
        holdings = float(params.get("数量", 0) or 0)
        cost_basis = float(params.get("成本", 0) or 0)
        current_value = float(params.get("现值", 0) or 0)
    except (TypeError, ValueError):
        return "⚠️ 数量/成本/现值必须是数字"

    db = get_db()
    dup = db.execute(
        "SELECT 1 FROM assets WHERE user_id = ? AND name = ?",
        (user_id, name),
    ).fetchone()
    if dup:
        return f"⚠️ 资产「{name}」已存在，请换个名称或使用更新接口修改"

    symbol = (params.get("代码") or "").strip() or None

    # security_auto：按 quote_source 尝试拉行情，避免用户手填市值
    if (type_def["shape"] == "security_auto" and type_def["quote_source"]
            and symbol and holdings > 0 and current_value <= 0):
        try:
            from services.quotes import get_quote
            q = get_quote(db, symbol, type_def["quote_source"], force=True)
            if q is not None:
                current_value = round(q.price * holdings, 2)
        except (ImportError, RuntimeError) as e:
            logger.warning("[invest_add_asset] quote fetch failed: %s", e)

    now = datetime.now().isoformat(timespec="seconds")
    try:
        db.execute(
            "INSERT INTO assets (user_id, name, type, symbol, holdings, cost_basis, "
            "current_value, currency, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'CNY', ?, ?, ?)",
            (user_id, name, atype, symbol,
             holdings, cost_basis, current_value,
             (params.get("备注") or "").strip() or None, now, now),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return f"⚠️ 资产「{name}」已存在"
    invalidate_user(user_id)
    tail = f"当前市值 ¥{current_value:.2f}" if current_value > 0 else "稍后可刷新行情自动更新市值"
    return f"✅ 已登记资产「{name}」（{atype}），{tail}"


def invest_update_value(user_id: int, params: dict[str, Any]) -> str:
    name = (params.get("名称") or "").strip()
    if not name:
        return "⚠️ 请提供资产名称"
    try:
        current_value = float(params.get("现值", 0) or 0)
    except (TypeError, ValueError):
        return "⚠️ 现值必须是数字"
    db = get_db()
    res = db.execute(
        "UPDATE assets SET current_value = ?, updated_at = ? WHERE user_id = ? AND name = ?",
        (current_value, datetime.now().isoformat(timespec="seconds"), user_id, name),
    )
    db.commit()
    invalidate_user(user_id)
    if res.rowcount == 0:
        return f"⚠️ 未找到名为「{name}」的资产"
    return f"✅ 已更新「{name}」现值为 ¥{current_value:.2f}"


def invest_add_goal(user_id: int, params: dict[str, Any]) -> str:
    name = (params.get("名称") or "").strip()
    if not name:
        return "⚠️ 请提供目标名称"
    try:
        target = float(params.get("目标金额", 0) or 0)
    except (TypeError, ValueError):
        return "⚠️ 目标金额必须是数字"
    if target <= 0:
        return "⚠️ 目标金额需大于 0"
    db = get_db()
    now = datetime.now().isoformat(timespec="seconds")
    db.execute(
        "INSERT INTO financial_goals (user_id, name, target_amount, deadline, "
        "current_progress, priority, note, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, name, target,
         (params.get("截止日期") or "").strip() or None,
         float(params.get("已完成", 0) or 0),
         int(params.get("优先级", 3) or 3),
         (params.get("备注") or "").strip() or None,
         now, now),
    )
    db.commit()
    deadline_str = f"，截止 {params.get('截止日期')}" if params.get("截止日期") else ""
    return f"✅ 已创建理财目标「{name}」目标金额 ¥{target:.2f}{deadline_str}"


def invest_portfolio_summary(user_id: int, params: dict[str, Any] | None = None) -> str:
    from services.portfolio import compute_allocation, compute_return
    db = get_db()
    rows = db.execute(
        "SELECT name, type, current_value, cost_basis FROM assets WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    if not rows:
        return "📊 暂无资产记录，先录入几项资产再回来分析吧。"
    assets = [dict(r) for r in rows]
    allo = compute_allocation(assets)
    ret = compute_return(assets)
    lines = [f"📊 投资组合总览：总市值 ¥{allo['total_value']:.2f}，累计回报 {ret['return_pct']:.2f}%"]
    lines.append("类型分布：")
    for row in allo["by_type"]:
        lines.append(f"  {row['type']}：¥{row['value']:.2f}（{row['pct']:.1f}%）")
    return "\n".join(lines)


def invest_analyze_portfolio(
    user_id: int,
    params: dict[str, Any] | None = None,
    llm: dict | None = None,
) -> str:
    """生成自然语言的投资组合诊断（调用 LLM）。"""
    from services.portfolio import (
        compute_allocation, compute_drift, compute_return, build_holding_details,
    )
    from services.llm import call_llm_portfolio_advice
    db = get_db()
    rows = db.execute(
        "SELECT name, type, symbol, holdings, current_value, cost_basis FROM assets WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    if not rows:
        return "📊 暂无资产记录，先录入几项资产再回来分析吧。"
    assets = [dict(r) for r in rows]
    allocation = compute_allocation(assets)
    returns = compute_return(assets)
    holdings = build_holding_details(assets)
    risk_row = db.execute(
        "SELECT level FROM risk_profiles WHERE user_id = ?", (user_id,),
    ).fetchone()
    risk_level = risk_row["level"] if risk_row else None
    drift = compute_drift(allocation, risk_level=risk_level)
    return call_llm_portfolio_advice(allocation, drift, returns, risk_level, llm=llm, holdings=holdings)


def invest_refresh_prices(user_id: int, params: dict[str, Any] | None = None) -> str:
    """强制刷新该用户股票/基金行情并更新 current_value。"""
    from services.quotes import refresh_user_assets
    stats = refresh_user_assets(get_db(), user_id, force=True)
    invalidate_user(user_id)
    if stats["updated"] == 0:
        return "ℹ️ 未更新任何资产（无股票/基金或缺少代码/持仓）"
    msg = f"🔄 已刷新 {stats['updated']} 项股票/基金行情"
    if stats["stale"]:
        msg += f"（其中 {stats['stale']} 项使用旧缓存）"
    return msg
