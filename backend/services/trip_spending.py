"""行程花费:把账本里属于某趟行程的条目算出来。

归属靠 records.trip_id / income.trip_id 显式记着,不靠日期现算——
出发前买的机票、回来才结的账、以及旅行当中在家产生的自动扣费,
光看日期都会算错。日期只用来做"批量归入"时的默认范围。
"""
from __future__ import annotations

from db import get_db


def _own_trip(user_id: int, trip_id: int):
    return get_db().execute(
        "SELECT * FROM trips WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (trip_id, user_id),
    ).fetchone()


def summary(user_id: int, trip_id: int) -> dict:
    """这趟的花费汇总:总额、按分类、按天,以及明细。"""
    db = get_db()
    spend = [dict(r) for r in db.execute(
        "SELECT id, category, amount, note, date FROM records "
        "WHERE user_id = ? AND trip_id = ? AND deleted_at IS NULL ORDER BY date, id",
        (user_id, trip_id),
    ).fetchall()]
    earn = [dict(r) for r in db.execute(
        "SELECT id, category, amount, note, date FROM income "
        "WHERE user_id = ? AND trip_id = ? AND deleted_at IS NULL ORDER BY date, id",
        (user_id, trip_id),
    ).fetchall()]

    by_cat: dict[str, float] = {}
    by_day: dict[str, float] = {}
    total = 0.0
    for r in spend:
        amt = float(r["amount"] or 0)
        total += amt
        by_cat[r["category"]] = round(by_cat.get(r["category"], 0) + amt, 2)
        by_day[r["date"]] = round(by_day.get(r["date"], 0) + amt, 2)

    refund = round(sum(float(r["amount"] or 0) for r in earn), 2)
    return {
        "total": round(total, 2),
        "refund": refund,
        "net": round(total - refund, 2),
        "count": len(spend) + len(earn),
        "by_category": sorted(
            ({"category": k, "amount": v} for k, v in by_cat.items()),
            key=lambda x: -x["amount"],
        ),
        "by_day": [{"date": k, "amount": by_day[k]} for k in sorted(by_day)],
        "records": spend,
        "income": earn,
    }


def attach_range(user_id: int, trip_id: int, start: str, end: str) -> dict:
    """把一段日期内、**还没归属到任何行程**的条目归到这趟。

    不抢别的行程的条目:两趟行程日期挨着甚至重叠时,后点的那次会把前一趟
    的账掀走,那种"越点越乱"比少归几条糟得多。要改归属就逐条改。
    """
    db = get_db()
    moved = 0
    for table in ("records", "income"):
        cur = db.execute(
            f"UPDATE {table} SET trip_id = ? "
            "WHERE user_id = ? AND trip_id IS NULL AND deleted_at IS NULL "
            "AND date >= ? AND date <= ?",
            (trip_id, user_id, start, end),
        )
        moved += cur.rowcount
    db.commit()
    return {"moved": moved}


def detach_all(user_id: int, trip_id: int) -> dict:
    db = get_db()
    n = 0
    for table in ("records", "income"):
        n += db.execute(
            f"UPDATE {table} SET trip_id = NULL WHERE user_id = ? AND trip_id = ?",
            (user_id, trip_id),
        ).rowcount
    db.commit()
    return {"moved": n}


def auto_trip_for(user_id: int, date: str) -> int | None:
    """这个日期落在哪趟行程里。

    只有**恰好一趟**覆盖时才返回——两趟重叠时猜错比不猜糟,
    宁可让用户自己归。
    """
    if not date:
        return None
    rows = get_db().execute(
        "SELECT id FROM trips WHERE user_id = ? AND deleted_at IS NULL "
        "AND start_date <= ? AND end_date >= ? LIMIT 2",
        (user_id, date, date),
    ).fetchall()
    return rows[0]["id"] if len(rows) == 1 else None


def validate_trip_id(user_id: int, raw):
    """把请求里传来的 trip_id 变成能写进库的值。

    None / 空串 表示"取消归属"。别的值必须是本人名下还在的行程,
    否则宁可报错也不要写进去——留下一个指向别人行程的 id,
    汇总时是查不出来的脏数据。
    """
    if raw in (None, "", 0, "0"):
        return None
    try:
        tid = int(raw)
    except (TypeError, ValueError):
        raise ValueError("trip_id 无效")
    if not _own_trip(user_id, tid):
        raise ValueError("行程不存在")
    return tid
