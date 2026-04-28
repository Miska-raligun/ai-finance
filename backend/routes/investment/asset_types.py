"""资产类型自管理：用户自己定义"股票/基金/现金/房产..."。"""
from __future__ import annotations

import sqlite3
from flask import g, jsonify, request

from auth import login_required
from cache import invalidate_user
from db import get_db

from ._common import (
    investment_bp, now_iso,
    load_asset_type, list_asset_types_db,
    VALID_SHAPES, VALID_QUOTE_SOURCES,
)


@investment_bp.route("/api/investment/asset-types", methods=["GET"])
@login_required
def list_asset_types():
    return jsonify(list_asset_types_db())


@investment_bp.route("/api/investment/asset-types", methods=["POST"])
@login_required
def create_asset_type():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    shape = (data.get("shape") or "").strip()
    quote_source = (data.get("quote_source") or "").strip() or None

    if not name:
        return jsonify({"error": "缺少类型名称"}), 400
    if shape not in VALID_SHAPES:
        return jsonify({"error": f"非法形态：{shape}"}), 400
    if shape == "security_auto":
        if quote_source not in VALID_QUOTE_SOURCES:
            return jsonify({"error": "security_auto 必须指定 quote_source=stock|fund"}), 400
    else:
        quote_source = None

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO asset_types (user_id, name, shape, quote_source, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (g.user_id, name, shape, quote_source, now_iso()),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": f"类型「{name}」已存在"}), 409
    invalidate_user(g.user_id)
    return jsonify({"id": cur.lastrowid, "success": True}), 201


@investment_bp.route("/api/investment/asset-types/<name>", methods=["DELETE"])
@login_required
def delete_asset_type(name: str):
    db = get_db()
    t = load_asset_type(name)
    if not t:
        return jsonify({"error": f"类型「{name}」不存在"}), 404
    in_use = db.execute(
        "SELECT COUNT(*) AS c FROM assets WHERE user_id = ? AND type = ?",
        (g.user_id, name),
    ).fetchone()["c"]
    if in_use > 0:
        return jsonify({
            "error": f"类型「{name}」仍有 {in_use} 项资产在使用，请先改为其他类型或删除这些资产",
            "in_use": in_use,
        }), 409
    db.execute(
        "DELETE FROM asset_types WHERE user_id = ? AND name = ?",
        (g.user_id, name),
    )
    db.commit()
    invalidate_user(g.user_id)
    return jsonify({"success": True})
