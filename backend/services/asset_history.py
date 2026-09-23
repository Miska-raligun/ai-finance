"""资产市值历史快照统一入口。

被 routes/investment/assets.py（create/update）、services/quotes.py
（refresh_user_assets）、services/asset_settle.py（sell）共用，保证任意
current_value 变化都会写一条历史。

去重策略：同一资产同一天只保留最后一条快照，避免高频刷新让表膨胀。
"""
from __future__ import annotations

from datetime import datetime


def snapshot(db, user_id: int, asset_id: int, value: float,
             *, recorded_at: str | None = None) -> None:
    """写入或更新当天的资产市值快照。

    - 同一 (asset_id, day) 已有记录 → UPDATE 覆盖（取最新）
    - 否则 INSERT 一条新行
    - value < 0 也接受（极少数对冲场景），但 NaN / None 会跳过
    """
    if value is None:
        return
    try:
        value = float(value)
    except (TypeError, ValueError):
        return

    now = recorded_at or datetime.now().isoformat(timespec="seconds")
    today = now[:10]
    cur = db.execute(
        "UPDATE asset_value_history SET value = ?, recorded_at = ? "
        "WHERE asset_id = ? AND substr(recorded_at, 1, 10) = ?",
        (value, now, asset_id, today),
    )
    if cur.rowcount == 0:
        db.execute(
            "INSERT INTO asset_value_history (user_id, asset_id, value, recorded_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, asset_id, value, now),
        )
