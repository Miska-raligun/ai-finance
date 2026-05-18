"""资产卖出 / 归档结算：写盈亏到 income / records，更新 / 删除资产。

REST 路由（routes/investment/assets.py）和 MCP 工具（mcp_server.py）共用。
所有函数接受 sqlite3 connection（来自 Flask g.db 或 MCP 直连），不直接 import
flask 上下文，方便在两端复用。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

PNL_INCOME_CATEGORY = "投资盈利"
PNL_EXPENSE_CATEGORY = "投资亏损"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _fmt_qty(q: float) -> str:
    """股票/基金/份额数量去掉冗余 0；整数则不显示小数。"""
    if abs(q - round(q)) < 1e-6:
        return str(int(round(q)))
    return f"{q:.4f}".rstrip("0").rstrip(".")


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

    if abs(pnl) < 0.005:
        return 0.0, "none"

    if pnl > 0:
        db.execute(
            "INSERT OR IGNORE INTO categories (user_id, name, type) VALUES (?, ?, '收入')",
            (user_id, PNL_INCOME_CATEGORY),
        )
        db.execute(
            "INSERT INTO income (user_id, category, amount, note, date) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, PNL_INCOME_CATEGORY, pnl, note, date),
        )
        return pnl, "income"

    db.execute(
        "INSERT OR IGNORE INTO categories (user_id, name, type) VALUES (?, ?, '支出')",
        (user_id, PNL_EXPENSE_CATEGORY),
    )
    db.execute(
        "INSERT INTO records (user_id, category, amount, note, date) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, PNL_EXPENSE_CATEGORY, abs(pnl), note, date),
    )
    return pnl, "expense"


class SettleError(ValueError):
    """所有入参或业务校验失败统一抛这个，调用方按需翻译成 HTTP 400 / MCP 错误文案。"""


def sell_asset(db, user_id: int, asset_id: int, *,
               price: float, quantity: float | None = None,
               fee: float = 0.0, date: str | None = None,
               note: str = "") -> dict[str, Any]:
    """部分或全部卖出。quantity=None 视为卖出全部持仓。"""
    row = db.execute(
        "SELECT id, name, type, holdings, cost_basis, current_value "
        "FROM assets WHERE id = ? AND user_id = ?",
        (asset_id, user_id),
    ).fetchone()
    if not row:
        raise SettleError("资产不存在")
    asset = dict(row)
    holdings = float(asset["holdings"] or 0)
    cost_basis = float(asset["cost_basis"] or 0)
    cur_value = float(asset["current_value"] or 0)
    if holdings <= 0:
        raise SettleError("该资产无持仓，请改用 archive_asset 直接结算")

    try:
        price = float(price)
    except (TypeError, ValueError):
        raise SettleError("卖出价必须是数字")
    if price <= 0:
        raise SettleError("卖出价必须大于 0")

    if quantity in (None, 0, "0", ""):
        sold_qty = holdings
    else:
        try:
            sold_qty = float(quantity)
        except (TypeError, ValueError):
            raise SettleError("数量必须是数字")
    if sold_qty <= 0 or sold_qty > holdings + 1e-6:
        raise SettleError(f"数量必须在 (0, {holdings}] 之间")

    try:
        fee = max(0.0, float(fee or 0))
    except (TypeError, ValueError):
        raise SettleError("手续费必须是数字")

    date = (date or datetime.now().strftime("%Y-%m-%d")).strip()
    user_note = (note or "").strip()

    proceeds = round(price * sold_qty - fee, 2)
    prorata_cost = round(cost_basis * sold_qty / holdings, 2)

    extra = f"卖出价 ¥{price:.4f}/股"
    if user_note:
        extra += " · " + user_note

    pnl, ledger_kind = _settle_pnl(
        db, user_id,
        asset_name=asset["name"], atype=asset["type"],
        sold_qty=sold_qty, proceeds=proceeds, cost=prorata_cost,
        fee=fee, date=date, action="卖出", extra_note=extra,
    )

    db.execute(
        "INSERT INTO asset_transactions "
        "(user_id, asset_id, kind, quantity, price, fee, date, note, created_at) "
        "VALUES (?, ?, 'sell', ?, ?, ?, ?, ?, ?)",
        (user_id, asset_id, sold_qty, price, fee, date,
         user_note or None, _now_iso()),
    )

    new_holdings = round(holdings - sold_qty, 6)
    if new_holdings <= 1e-6:
        db.execute(
            "DELETE FROM assets WHERE id = ? AND user_id = ?",
            (asset_id, user_id),
        )
        new_holdings = 0
    else:
        new_cost = round(cost_basis - prorata_cost, 2)
        new_value = round(cur_value * new_holdings / holdings, 2) if holdings > 0 else 0
        db.execute(
            "UPDATE assets SET holdings = ?, cost_basis = ?, current_value = ?, "
            "updated_at = ? WHERE id = ? AND user_id = ?",
            (new_holdings, new_cost, new_value, _now_iso(), asset_id, user_id),
        )
        # 部分卖出后市值变化也写入历史，保证 /history 折线连续
        from services.asset_history import snapshot
        snapshot(db, user_id, asset_id, new_value)

    db.commit()
    return {
        "asset_name": asset["name"],
        "asset_type": asset["type"],
        "sold_qty": sold_qty,
        "price": price,
        "fee": fee,
        "proceeds": proceeds,
        "cost": prorata_cost,
        "pnl": pnl,
        "ledger": ledger_kind,
        "remaining_holdings": new_holdings,
    }


def archive_asset(db, user_id: int, asset_id: int, *,
                  date: str | None = None, note: str = "") -> dict[str, Any]:
    """归档：以当前 current_value 作为出场金额一次性结算盈亏，资产删除。"""
    row = db.execute(
        "SELECT id, name, type, holdings, cost_basis, current_value "
        "FROM assets WHERE id = ? AND user_id = ?",
        (asset_id, user_id),
    ).fetchone()
    if not row:
        raise SettleError("资产不存在")
    asset = dict(row)
    holdings = float(asset["holdings"] or 0)
    cost_basis = float(asset["cost_basis"] or 0)
    proceeds = float(asset["current_value"] or 0)
    date = (date or datetime.now().strftime("%Y-%m-%d")).strip()
    user_note = (note or "").strip()
    extra = f"按归档时市值 ¥{proceeds:.2f} 结算"
    if user_note:
        extra += " · " + user_note

    pnl, ledger_kind = _settle_pnl(
        db, user_id,
        asset_name=asset["name"], atype=asset["type"],
        sold_qty=holdings if holdings > 0 else 1,
        proceeds=proceeds, cost=cost_basis,
        fee=0, date=date, action="归档", extra_note=extra,
    )

    db.execute("DELETE FROM assets WHERE id = ? AND user_id = ?",
               (asset_id, user_id))
    db.execute("DELETE FROM asset_transactions WHERE asset_id = ? AND user_id = ?",
               (asset_id, user_id))
    db.commit()
    return {
        "asset_name": asset["name"],
        "asset_type": asset["type"],
        "proceeds": proceeds,
        "cost": cost_basis,
        "pnl": pnl,
        "ledger": ledger_kind,
    }
