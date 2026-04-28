"""支出记录相关 handler：add_record / search_records / delete_record / category_sum。"""
from __future__ import annotations

from typing import Any

from cache import invalidate_user
from constants import (
    CATEGORY_EXPENSE, CATEGORY_INCOME,
    PARAM_AMOUNT, PARAM_CATEGORY, PARAM_DATE, PARAM_NOTE,
)
from db import cleanup_empty_category, get_db

from ._common import today_str


def add_record(user_id: int, params: dict[str, Any]) -> str:
    db = get_db()
    category = params.get(PARAM_CATEGORY, "").strip()
    note = params.get(PARAM_NOTE, "").strip()
    amount = float(params.get(PARAM_AMOUNT, 0))

    date = params.get(PARAM_DATE, "").strip()
    if not date:
        date = today_str()

    if not category or not amount:
        return "⚠️ 分类和金额不能为空"

    row = db.execute(
        "SELECT type FROM categories WHERE name = ? AND user_id = ?",
        (category, user_id)
    ).fetchone()
    if row:
        if row['type'] == CATEGORY_INCOME:
            return f"⚠️ 分类「{category}」已被设为收入来源，不能作为支出使用，请更换分类名。"
    else:
        db.execute("INSERT INTO categories (user_id, name, type) VALUES (?, ?, ?)",
                   (user_id, category, CATEGORY_EXPENSE))

    # 写入前先计算异常分（基于历史，不含本笔）
    from services.anomaly import detect as _detect_anomaly
    anomaly = _detect_anomaly(user_id, category, amount, date)

    db.execute(
        "INSERT INTO records (user_id, category, amount, note, date, anomaly_score, anomaly_flag) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, category, amount, note, date, anomaly["score"], anomaly["flag"])
    )
    db.commit()
    invalidate_user(user_id)

    msg = f"✅ 成功记录一笔消费：你在「{category}」方面支出了 ¥{amount}，备注为「{note}」，日期为 {date}。"
    if anomaly["flag"] and anomaly["reason"]:
        msg += f"\n🚨 异常提醒：{anomaly['reason']}"

    # 预算预警
    month = date[:7]
    budget_row = db.execute(
        "SELECT amount FROM budgets WHERE user_id = ? AND category = ? AND month = ?",
        (user_id, category, month),
    ).fetchone()
    if budget_row:
        budget_amount = float(budget_row["amount"])
        spent_total = float(db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM records "
            "WHERE user_id = ? AND category = ? AND strftime('%Y-%m', date) = ?",
            (user_id, category, month),
        ).fetchone()[0])
        remaining = budget_amount - spent_total
        pct = spent_total / budget_amount * 100 if budget_amount > 0 else 0
        if remaining < 0:
            msg += (
                f"\n⚠️ 注意：「{category}」本月已超预算！"
                f"预算 ¥{budget_amount}，已花 ¥{spent_total:.2f}，超支 ¥{abs(remaining):.2f}。"
            )
        elif pct >= 80:
            msg += (
                f"\n⚠️ 提醒：「{category}」本月预算已用 {pct:.0f}%，"
                f"剩余 ¥{remaining:.2f}，请注意控制支出。"
            )

    return msg


def search_records(user_id: int, params: dict[str, Any]) -> str:
    """列出支出明细（含 ID），供 LLM 先查看再决定删除哪条。"""
    db = get_db()
    category = params.get(PARAM_CATEGORY, "").strip()
    time_range = params.get("时间范围", "").strip()
    limit = min(20, int(params.get("条数", 10)))

    q = "SELECT id, date, category, amount, note FROM records WHERE user_id=?"
    args: list[Any] = [user_id]
    if category:
        q += " AND category=?"; args.append(category)
    if len(time_range) == 10:    # YYYY-MM-DD
        q += " AND date=?"; args.append(time_range)
    elif len(time_range) == 7:   # YYYY-MM
        q += " AND strftime('%Y-%m', date)=?"; args.append(time_range)
    elif len(time_range) == 4:   # YYYY
        q += " AND strftime('%Y', date)=?"; args.append(time_range)
    keyword = params.get("关键词", "").strip()
    if keyword:
        q += " AND note LIKE ?"; args.append(f"%{keyword}%")
    q += " ORDER BY id DESC LIMIT ?"; args.append(limit)

    rows = db.execute(q, args).fetchall()
    if not rows:
        return "暂无符合条件的支出记录。"
    return "\n".join(
        f"ID:{r['id']} | {r['date']} | {r['category']} | ¥{r['amount']} | {r['note']}"
        for r in rows
    )


def delete_record(user_id: int, params: dict[str, Any]) -> str:
    """按记录 ID 删除一条支出记录。"""
    db = get_db()
    record_id = params.get("记录ID")
    if not record_id:
        return "⚠️ 请提供「记录ID」。可先调用 search_records 查询获取ID。"
    row = db.execute(
        "SELECT id, category, amount, date, note FROM records WHERE id=? AND user_id=?",
        (int(record_id), user_id)
    ).fetchone()
    if not row:
        return f"❌ 未找到 ID:{record_id} 的支出记录（或不属于当前用户）。"
    category = row['category']
    db.execute("DELETE FROM records WHERE id=? AND user_id=?", (int(record_id), user_id))
    db.commit()
    cleanup_empty_category(user_id, category)
    invalidate_user(user_id)
    return f"✅ 已删除支出 ID:{record_id}，{row['date']} 「{category}」¥{row['amount']}（备注：{row['note']}）"


def category_sum(user_id: int, params: dict[str, Any]) -> str:
    category = params.get(PARAM_CATEGORY)
    start_date = params.get("开始时间")
    end_date = params.get("结束时间")

    db = get_db()
    query = "SELECT SUM(amount) FROM records WHERE user_id = ?"
    args: list[Any] = [user_id]

    if category:
        query += " AND category = ?"
        args.append(category)
    if start_date:
        query += " AND date >= ?"
        args.append(start_date)
    if end_date:
        query += " AND date <= ?"
        args.append(end_date)

    total = db.execute(query, args).fetchone()[0] or 0.0
    scope = f"{start_date} 至 {end_date}" if start_date and end_date else "所选范围内"
    if category:
        return f"📊 你在 {scope} 的「{category}」支出为 ¥{total:.2f}"
    return f"📊 你在 {scope} 的总支出为 ¥{total:.2f}"
