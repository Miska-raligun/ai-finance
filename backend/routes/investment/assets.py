"""资产 CRUD + 行情刷新 + 卖出 / 归档结算。"""
from __future__ import annotations

import sqlite3
from flask import g, jsonify, request

from auth import login_required
from cache import invalidate_user
from db import get_db
from services.quotes import get_quote, refresh_user_assets

from ._common import (
    investment_bp, now_iso,
    load_asset_type, fetch_assets,
)


@investment_bp.route("/api/investment/assets", methods=["GET"])
@login_required
def list_assets():
    return jsonify(fetch_assets())


@investment_bp.route("/api/investment/assets", methods=["POST"])
@login_required
def create_asset():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    atype = (data.get("type") or "").strip()
    if not name:
        return jsonify({"error": "缺少资产名称"}), 400
    if not atype:
        return jsonify({"error": "缺少资产类型"}), 400
    type_def = load_asset_type(atype)
    if not type_def:
        return jsonify({"error": f"类型「{atype}」未定义，请先在类型管理中创建"}), 400
    try:
        holdings = float(data.get("holdings") or 0)
        cost_basis = float(data.get("cost_basis") or 0)
        current_value = float(data.get("current_value") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "数值字段必须为数字"}), 400

    symbol = (data.get("symbol") or "").strip() or None
    db = get_db()

    # security_auto：如果用户没填市值但给了代码+持仓，按 quote_source 尝试自动拉行情
    if (type_def["shape"] == "security_auto" and type_def["quote_source"]
            and symbol and holdings > 0 and current_value <= 0):
        q = get_quote(db, symbol, type_def["quote_source"], force=True)
        if q is not None:
            current_value = round(q.price * holdings, 2)

    try:
        cur = db.execute(
            "INSERT INTO assets (user_id, name, type, symbol, holdings, cost_basis, "
            "current_value, currency, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                g.user_id, name, atype, symbol,
                holdings, cost_basis, current_value,
                (data.get("currency") or "CNY").strip() or "CNY",
                (data.get("notes") or "").strip() or None,
                now_iso(), now_iso(),
            ),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": f"资产「{name}」已存在，请换个名称或编辑已有资产"}), 409
    invalidate_user(g.user_id)
    return jsonify({"id": cur.lastrowid, "success": True}), 201


@investment_bp.route("/api/investment/assets/<int:asset_id>", methods=["PATCH"])
@login_required
def update_asset(asset_id: int):
    data = request.get_json() or {}
    db = get_db()
    row = db.execute(
        "SELECT id FROM assets WHERE id = ? AND user_id = ?", (asset_id, g.user_id),
    ).fetchone()
    if not row:
        return jsonify({"error": "资产不存在"}), 404

    allowed = {"name", "type", "symbol", "holdings", "cost_basis", "current_value", "currency", "notes"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({"error": "无可更新字段"}), 400
    if "type" in updates and not load_asset_type(updates["type"]):
        return jsonify({"error": f"类型「{updates['type']}」未定义"}), 400

    sets = ", ".join(f"{k} = ?" for k in updates) + ", updated_at = ?"
    values = list(updates.values()) + [now_iso(), asset_id, g.user_id]
    try:
        db.execute(f"UPDATE assets SET {sets} WHERE id = ? AND user_id = ?", values)
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "资产名称与已有资产重复"}), 409
    invalidate_user(g.user_id)
    return jsonify({"success": True})


@investment_bp.route("/api/investment/assets/<int:asset_id>", methods=["DELETE"])
@login_required
def delete_asset(asset_id: int):
    db = get_db()
    res = db.execute(
        "DELETE FROM assets WHERE id = ? AND user_id = ?", (asset_id, g.user_id),
    )
    db.execute(
        "DELETE FROM asset_transactions WHERE asset_id = ? AND user_id = ?",
        (asset_id, g.user_id),
    )
    db.commit()
    invalidate_user(g.user_id)
    if res.rowcount == 0:
        return jsonify({"error": "资产不存在"}), 404
    return jsonify({"success": True})


@investment_bp.route("/api/investment/refresh-prices", methods=["POST"])
@login_required
def refresh_prices():
    db = get_db()
    stats = refresh_user_assets(db, g.user_id, force=True)
    invalidate_user(g.user_id)
    return jsonify(stats)


# ===== 卖出 / 归档：薄包装，核心结算逻辑在 services/asset_settle.py
# 与 mcp_server.py 共用，保持单一事实来源 =====

@investment_bp.route("/api/investment/assets/<int:asset_id>/sell", methods=["POST"])
@login_required
def sell_asset(asset_id: int):
    """部分或全部卖出：按摊销成本计算盈亏，写入 income / records，更新持仓。"""
    from services.asset_settle import sell_asset as _sell, SettleError
    data = request.get_json() or {}
    try:
        result = _sell(
            get_db(), g.user_id, asset_id,
            price=data.get("price") or 0,
            quantity=data.get("quantity"),
            fee=data.get("fee") or 0,
            date=data.get("date"),
            note=data.get("note") or "",
        )
    except SettleError as e:
        # 资产不存在 → 404；其它入参问题 → 400
        code = 404 if "不存在" in str(e) else 400
        return jsonify({"error": str(e)}), code
    invalidate_user(g.user_id)
    return jsonify({"success": True, **result})


@investment_bp.route("/api/investment/assets/<int:asset_id>/archive", methods=["POST"])
@login_required
def archive_asset(asset_id: int):
    """归档：以当前 current_value 作为出场金额一次性结算盈亏，资产删除。"""
    from services.asset_settle import archive_asset as _archive, SettleError
    data = request.get_json() or {}
    try:
        result = _archive(
            get_db(), g.user_id, asset_id,
            date=data.get("date"),
            note=data.get("note") or "",
        )
    except SettleError as e:
        code = 404 if "不存在" in str(e) else 400
        return jsonify({"error": str(e)}), code
    invalidate_user(g.user_id)
    return jsonify({"success": True, **result})
