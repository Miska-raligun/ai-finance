"""资产交易流水：买/卖/分红/调整。"""
from __future__ import annotations

from datetime import datetime
from flask import g, jsonify, request

from auth import login_required
from cache import invalidate_user
from db import get_db

from ._common import investment_bp, now_iso, TX_KINDS


@investment_bp.route("/api/investment/transactions", methods=["GET"])
@login_required
def list_transactions():
    asset_id = request.args.get("asset_id")
    db = get_db()
    cols = ("t.id, t.asset_id, a.name AS asset_name, t.kind, t.quantity, t.price, "
            "t.fee, t.date, t.note, t.created_at")
    if asset_id:
        rows = db.execute(
            f"SELECT {cols} FROM asset_transactions t "
            "JOIN assets a ON a.id = t.asset_id "
            "WHERE t.user_id = ? AND t.asset_id = ? ORDER BY t.date DESC, t.id DESC",
            (g.user_id, asset_id),
        ).fetchall()
    else:
        rows = db.execute(
            f"SELECT {cols} FROM asset_transactions t "
            "JOIN assets a ON a.id = t.asset_id "
            "WHERE t.user_id = ? ORDER BY t.date DESC, t.id DESC LIMIT 200",
            (g.user_id,),
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@investment_bp.route("/api/investment/transactions", methods=["POST"])
@login_required
def add_transaction():
    data = request.get_json() or {}
    try:
        asset_id = int(data.get("asset_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "缺少 asset_id"}), 400
    kind = (data.get("kind") or "").strip()
    if kind not in TX_KINDS:
        return jsonify({"error": f"非法交易类型：{kind}"}), 400
    try:
        quantity = float(data.get("quantity") or 0)
        price = float(data.get("price") or 0)
        fee = float(data.get("fee") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "数值字段必须为数字"}), 400
    date = (data.get("date") or datetime.now().strftime("%Y-%m-%d")).strip()

    db = get_db()
    owns = db.execute(
        "SELECT id FROM assets WHERE id = ? AND user_id = ?", (asset_id, g.user_id),
    ).fetchone()
    if not owns:
        return jsonify({"error": "资产不存在"}), 404

    db.execute(
        "INSERT INTO asset_transactions (user_id, asset_id, kind, quantity, price, fee, date, note, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (g.user_id, asset_id, kind, quantity, price, fee, date,
         (data.get("note") or "").strip() or None, now_iso()),
    )
    db.commit()
    invalidate_user(g.user_id)
    return jsonify({"success": True}), 201
