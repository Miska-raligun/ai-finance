"""资产 CRUD + 行情刷新 + 卖出 / 归档结算。"""
from __future__ import annotations

import sqlite3
from datetime import datetime
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


# ===== 卖出 / 归档：自动把盈亏结算到 income / records =====

# 自动建分类时使用的中文名称。与 constants.CATEGORY_INCOME / CATEGORY_EXPENSE 配合。
_PNL_INCOME_CATEGORY = "投资盈利"
_PNL_EXPENSE_CATEGORY = "投资亏损"


def _settle_pnl(db, user_id: int, *, asset_name: str, atype: str,
                sold_qty: float, proceeds: float, cost: float,
                fee: float, date: str, action: str, extra_note: str = "") -> tuple[float, str]:
    """把一次出场的盈亏写到收入或支出表，自动建分类。

    返回 (pnl, ledger_kind)。ledger_kind ∈ {"income", "expense", "none"}。
    备注里把成本 / 出场金额 / 手续费 / 数量都拼出来，方便日后回看时定位资产。
    """
    pnl = round(proceeds - cost, 2)
    parts = [
        f"{action}「{asset_name}」（{atype}）",
        f"数量 {_fmt_qty(sold_qty)}",
        f"成本 ¥{cost:.2f}",
        f"出场金额 ¥{proceeds:.2f}",
    ]
    if fee > 0:
        parts.append(f"费用 ¥{fee:.2f}")
    if extra_note:
        parts.append(extra_note)
    note = " · ".join(parts)

    # 盈亏小于 1 分钱视为持平，不写记录避免噪音
    if abs(pnl) < 0.005:
        return 0.0, "none"

    if pnl > 0:
        db.execute(
            "INSERT OR IGNORE INTO categories (user_id, name, type) VALUES (?, ?, '收入')",
            (user_id, _PNL_INCOME_CATEGORY),
        )
        db.execute(
            "INSERT INTO income (user_id, category, amount, note, date) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, _PNL_INCOME_CATEGORY, pnl, note, date),
        )
        return pnl, "income"

    db.execute(
        "INSERT OR IGNORE INTO categories (user_id, name, type) VALUES (?, ?, '支出')",
        (user_id, _PNL_EXPENSE_CATEGORY),
    )
    db.execute(
        "INSERT INTO records (user_id, category, amount, note, date) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, _PNL_EXPENSE_CATEGORY, abs(pnl), note, date),
    )
    return pnl, "expense"


def _fmt_qty(q: float) -> str:
    """股票/基金/份额数量去掉冗余 0；整数则不显示小数。"""
    if abs(q - round(q)) < 1e-6:
        return str(int(round(q)))
    return f"{q:.4f}".rstrip("0").rstrip(".")


@investment_bp.route("/api/investment/assets/<int:asset_id>/sell", methods=["POST"])
@login_required
def sell_asset(asset_id: int):
    """部分或全部卖出：按摊销成本计算盈亏，写入 income / records，更新持仓。"""
    data = request.get_json() or {}
    db = get_db()
    row = db.execute(
        "SELECT id, name, type, holdings, cost_basis, current_value "
        "FROM assets WHERE id = ? AND user_id = ?",
        (asset_id, g.user_id),
    ).fetchone()
    if not row:
        return jsonify({"error": "资产不存在"}), 404
    asset = dict(row)
    holdings = float(asset["holdings"] or 0)
    cost_basis = float(asset["cost_basis"] or 0)
    cur_value = float(asset["current_value"] or 0)
    if holdings <= 0:
        return jsonify({"error": "该资产无持仓，请改用「归档」直接结算"}), 400

    try:
        price = float(data.get("price") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "卖出价必须是数字"}), 400
    if price <= 0:
        return jsonify({"error": "卖出价必须大于 0"}), 400

    qty_input = data.get("quantity")
    if qty_input in (None, "", 0, "0"):
        sold_qty = holdings
    else:
        try:
            sold_qty = float(qty_input)
        except (TypeError, ValueError):
            return jsonify({"error": "数量必须是数字"}), 400
    if sold_qty <= 0 or sold_qty > holdings + 1e-6:
        return jsonify({"error": f"数量必须在 (0, {holdings}] 之间"}), 400

    try:
        fee = max(0.0, float(data.get("fee") or 0))
    except (TypeError, ValueError):
        return jsonify({"error": "手续费必须是数字"}), 400

    date = (data.get("date") or datetime.now().strftime("%Y-%m-%d")).strip()
    user_note = (data.get("note") or "").strip()

    proceeds = round(price * sold_qty - fee, 2)
    prorata_cost = round(cost_basis * sold_qty / holdings, 2)

    extra = f"卖出价 ¥{price:.4f}/股"
    if user_note:
        extra += " · " + user_note

    pnl, ledger_kind = _settle_pnl(
        db, g.user_id,
        asset_name=asset["name"], atype=asset["type"],
        sold_qty=sold_qty, proceeds=proceeds, cost=prorata_cost,
        fee=fee, date=date, action="卖出", extra_note=extra,
    )

    # 写交易流水（保留即便资产被删，便于审计）
    db.execute(
        "INSERT INTO asset_transactions "
        "(user_id, asset_id, kind, quantity, price, fee, date, note, created_at) "
        "VALUES (?, ?, 'sell', ?, ?, ?, ?, ?, ?)",
        (g.user_id, asset_id, sold_qty, price, fee, date,
         user_note or None, now_iso()),
    )

    # 更新持仓 / 成本 / 现值
    new_holdings = round(holdings - sold_qty, 6)
    if new_holdings <= 1e-6:
        db.execute(
            "DELETE FROM assets WHERE id = ? AND user_id = ?",
            (asset_id, g.user_id),
        )
        new_holdings = 0
    else:
        new_cost = round(cost_basis - prorata_cost, 2)
        # 现值按比例缩减；自动行情类下次刷新会被覆盖，没影响
        new_value = round(cur_value * new_holdings / holdings, 2) if holdings > 0 else 0
        db.execute(
            "UPDATE assets SET holdings = ?, cost_basis = ?, current_value = ?, "
            "updated_at = ? WHERE id = ? AND user_id = ?",
            (new_holdings, new_cost, new_value, now_iso(), asset_id, g.user_id),
        )

    db.commit()
    invalidate_user(g.user_id)
    return jsonify({
        "success": True,
        "pnl": pnl,
        "ledger": ledger_kind,
        "remaining_holdings": new_holdings,
        "proceeds": proceeds,
        "cost": prorata_cost,
    })


@investment_bp.route("/api/investment/assets/<int:asset_id>/archive", methods=["POST"])
@login_required
def archive_asset(asset_id: int):
    """归档：以当前 current_value 作为出场金额一次性结算盈亏，资产删除。

    用于现金类 / 不打算细记录卖出价的整笔资产，或者用户想把停止追踪的资产
    一次性平掉。
    """
    data = request.get_json() or {}
    db = get_db()
    row = db.execute(
        "SELECT id, name, type, holdings, cost_basis, current_value "
        "FROM assets WHERE id = ? AND user_id = ?",
        (asset_id, g.user_id),
    ).fetchone()
    if not row:
        return jsonify({"error": "资产不存在"}), 404
    asset = dict(row)
    holdings = float(asset["holdings"] or 0)
    cost_basis = float(asset["cost_basis"] or 0)
    proceeds = float(asset["current_value"] or 0)
    date = (data.get("date") or datetime.now().strftime("%Y-%m-%d")).strip()
    user_note = (data.get("note") or "").strip()
    extra = "按归档时市值 ¥{:.2f} 结算".format(proceeds)
    if user_note:
        extra += " · " + user_note

    pnl, ledger_kind = _settle_pnl(
        db, g.user_id,
        asset_name=asset["name"], atype=asset["type"],
        sold_qty=holdings if holdings > 0 else 1,  # 现金类不显示数量也无所谓
        proceeds=proceeds, cost=cost_basis,
        fee=0, date=date, action="归档", extra_note=extra,
    )

    db.execute(
        "DELETE FROM assets WHERE id = ? AND user_id = ?",
        (asset_id, g.user_id),
    )
    db.execute(
        "DELETE FROM asset_transactions WHERE asset_id = ? AND user_id = ?",
        (asset_id, g.user_id),
    )
    db.commit()
    invalidate_user(g.user_id)
    return jsonify({
        "success": True,
        "pnl": pnl,
        "ledger": ledger_kind,
        "proceeds": proceeds,
        "cost": cost_basis,
    })
