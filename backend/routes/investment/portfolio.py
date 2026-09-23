"""投资组合概览 + 再平衡建议。"""
from __future__ import annotations

from flask import g, jsonify, request

from auth import login_required
from db import get_db
from services.portfolio import compute_allocation, compute_return, compute_top_movers
from services.quotes import refresh_user_assets

from ._common import (
    investment_bp,
    fetch_assets, list_asset_types_db, load_llm_cfg,
)


@investment_bp.route("/api/investment/portfolio", methods=["GET"])
@login_required
def portfolio_summary():
    db = get_db()
    want_refresh = request.args.get("refresh", "").lower() in {"1", "true", "yes"}
    quote_stats = refresh_user_assets(db, g.user_id) if want_refresh else None
    assets = fetch_assets()
    allocation = compute_allocation(assets)
    returns = compute_return(assets)
    movers = compute_top_movers(assets)

    risk_row = db.execute(
        "SELECT level FROM risk_profiles WHERE user_id = ?", (g.user_id,),
    ).fetchone()
    risk_level = risk_row["level"] if risk_row else None

    return jsonify({
        "total_value": allocation["total_value"],
        "allocation": allocation,
        "returns": returns,
        "top_movers": movers,
        "risk_level": risk_level,
        "asset_count": len(assets),
        "quotes": quote_stats,
    })


@investment_bp.route("/api/investment/rebalance", methods=["POST"])
@login_required
def rebalance():
    """按需向 LLM 请求一次再平衡建议。

    body: {"force": false}；force=true 时跳过缓存。
    返回 {targets, rationale, drift, cached_at, source}。
    """
    from services.rebalance import suggest_rebalance
    data = request.get_json(silent=True) or {}
    force = bool(data.get("force"))
    llm_cfg = load_llm_cfg(data)

    db = get_db()
    assets = fetch_assets()
    allocation = compute_allocation(assets)
    risk_row = db.execute(
        "SELECT level FROM risk_profiles WHERE user_id = ?", (g.user_id,),
    ).fetchone()
    risk_level = risk_row["level"] if risk_row else None
    types = list_asset_types_db()

    result = suggest_rebalance(
        db, g.user_id, allocation, risk_level, types,
        llm=llm_cfg, force=force,
    )
    return jsonify({**result, "risk_level": risk_level})
