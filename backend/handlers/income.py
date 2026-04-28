"""收入相关 handler：add_income / query_income / delete_income。"""
from __future__ import annotations

from typing import Any

from cache import invalidate_user
from constants import (
    CATEGORY_EXPENSE, CATEGORY_INCOME,
    PARAM_AMOUNT, PARAM_CATEGORY, PARAM_DATE, PARAM_NOTE,
)
from db import cleanup_empty_category, get_db

from ._common import today_str


def add_income(user_id: int, params: dict[str, Any]) -> str:
    db = get_db()
    category = params.get(PARAM_CATEGORY, "").strip()
    note = params.get(PARAM_NOTE, "").strip()
    amount = float(params.get(PARAM_AMOUNT, 0))

    date = params.get(PARAM_DATE, "").strip()
    if not date:
        date = today_str()

    if not category or not amount:
        return "⚠️ 收入的来源和金额不能为空"

    row = db.execute(
        "SELECT type FROM categories WHERE name = ? AND user_id = ?",
        (category, user_id)
    ).fetchone()
    if row:
        if row['type'] == CATEGORY_EXPENSE:
            return f"⚠️ 「{category}」已作为支出分类存在，不能记录为收入来源，请更换名称。"
    else:
        db.execute(
            "INSERT INTO categories (user_id, name, type) VALUES (?, ?, ?)",
            (user_id, category, CATEGORY_INCOME)
        )

    db.execute(
        "INSERT INTO income (user_id, category, amount, note, date) VALUES (?, ?, ?, ?, ?)",
        (user_id, category, amount, note, date)
    )
    db.commit()
    invalidate_user(user_id)

    return f"✅ 成功记录一笔收入：你从「{category}」获得了 ¥{amount}，备注为「{note}」，日期为 {date}。"


def query_income(user_id: int, params: dict[str, Any]) -> str:
    db = get_db()
    category = params.get(PARAM_CATEGORY, "").strip()
    time_range = params.get("时间范围", "").strip()
    show_all = params.get("全部", "") == "是"

    if show_all:
        results = [dict(r) for r in db.execute(
            "SELECT * FROM income WHERE user_id = ? ORDER BY date DESC",
            (user_id,)
        ).fetchall()]
        total = sum(float(r["amount"]) for r in results)
        reply = f"📊 当前共记录 {len(results)} 笔收入，总计 ¥{total:.2f}\n"
        for r in results[:10]:
            reply += f"📌 ID:{r['id']} {r['date']} - 来源「{r['category']}」收入 ¥{r['amount']}（备注：{r['note']}）\n"
        return reply + ("...（仅展示前10条）" if len(results) > 10 else "")

    query = "SELECT SUM(amount) AS total FROM income WHERE user_id = ?"
    args: list[Any] = [user_id]

    if time_range:
        if len(time_range) == 7:
            query += " AND strftime('%Y-%m', date) = ?"
            args.append(time_range)
        elif len(time_range) == 4:
            query += " AND strftime('%Y', date) = ?"
            args.append(time_range)

    if category:
        query += " AND category = ?"
        args.append(category)

    row = db.execute(query, tuple(args)).fetchone()
    total = float(row["total"] or 0)

    scope = ""
    if time_range:
        scope += f"{time_range} "
    if category:
        scope += f"来源「{category}」的"
    else:
        scope += "总"

    return f"💰 {scope}收入为 ¥{total:.2f}"


def delete_income(user_id: int, params: dict[str, Any]) -> str:
    """按记录 ID 删除一条收入记录。"""
    db = get_db()
    income_id = params.get("收入ID")
    if not income_id:
        return "⚠️ 请提供「收入ID」。可先调用 query_income（全部=是）查询获取ID。"
    row = db.execute(
        "SELECT id, category, amount, date, note FROM income WHERE id=? AND user_id=?",
        (int(income_id), user_id)
    ).fetchone()
    if not row:
        return f"❌ 未找到 ID:{income_id} 的收入记录（或不属于当前用户）。"
    category = row['category']
    db.execute("DELETE FROM income WHERE id=? AND user_id=?", (int(income_id), user_id))
    db.commit()
    cleanup_empty_category(user_id, category)
    invalidate_user(user_id)
    return f"✅ 已删除收入 ID:{income_id}，{row['date']} 「{category}」¥{row['amount']}（备注：{row['note']}）"
