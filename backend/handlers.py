from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

from constants import (
    CATEGORY_EXPENSE,
    CATEGORY_INCOME,
    PARAM_AMOUNT,
    PARAM_CATEGORY,
    PARAM_DATE,
    PARAM_MONTH,
    PARAM_NOTE,
)
from db import get_db, cleanup_empty_category
from cache import invalidate_user

logger = logging.getLogger(__name__)
llm_logger = logging.getLogger("llm_budget_suggest")
llm_logger.setLevel(logging.INFO)
if not llm_logger.handlers:
    handler = logging.FileHandler("llm_budget_suggest.log", encoding="utf-8")
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    llm_logger.addHandler(handler)


def add_record(user_id: int, params: dict[str, Any]) -> str:
    db = get_db()
    category = params.get(PARAM_CATEGORY, "").strip()
    note = params.get(PARAM_NOTE, "").strip()
    amount = float(params.get(PARAM_AMOUNT, 0))

    date = params.get(PARAM_DATE, "").strip()
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

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
        db.execute("INSERT INTO categories (user_id, name, type) VALUES (?, ?, ?)", (user_id, category, CATEGORY_EXPENSE))

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

    # 预算预警：查询该分类本月预算
    month = date[:7]  # "YYYY-MM"
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


def add_income(user_id: int, params: dict[str, Any]) -> str:
    db = get_db()
    category = params.get(PARAM_CATEGORY, "").strip()
    note = params.get(PARAM_NOTE, "").strip()
    amount = float(params.get(PARAM_AMOUNT, 0))

    date = params.get(PARAM_DATE, "").strip()
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

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


def set_budget(user_id: int, params: dict[str, Any]) -> str:
    logger.debug("LLM 预算参数: %s", params)

    category = params.get(PARAM_CATEGORY)
    amount = params.get(PARAM_AMOUNT) or params.get("预算")
    cycle = params.get("周期", "月")

    if not category or amount is None:
        return "⚠️ 设置预算失败，缺少分类或金额"

    db = get_db()

    row = db.execute(
        "SELECT type FROM categories WHERE name = ? AND user_id = ?",
        (category, user_id)
    ).fetchone()
    if row:
        if row['type'] != CATEGORY_EXPENSE:
            return f"⚠️ 分类「{category}」不是支出分类，无法设置预算。"
    else:
        db.execute(
            "INSERT INTO categories (user_id, name, type) VALUES (?, ?, ?)",
            (user_id, category, CATEGORY_EXPENSE)
        )

    db.execute(
        "INSERT OR REPLACE INTO budgets (user_id, category, amount, cycle, month) VALUES (?, ?, ?, ?, ?)",
        (user_id, category, float(amount), cycle, datetime.now().strftime("%Y-%m"))
    )
    db.commit()

    return f"✅ 已为「{category}」设置 {cycle} 预算 ¥{amount}。理性消费，快乐生活！"


def update_budget(user_id: int, params: dict[str, Any]) -> str:
    category = params.get(PARAM_CATEGORY)
    amount = params.get(PARAM_AMOUNT) or params.get("预算")
    cycle = params.get("周期", "月")

    if not category or amount is None:
        return "⚠️ 更新预算失败，缺少分类或金额"

    db = get_db()

    row = db.execute(
        "SELECT type FROM categories WHERE name = ? AND user_id = ?",
        (category, user_id)
    ).fetchone()
    if row:
        if row['type'] != CATEGORY_EXPENSE:
            return f"⚠️ 分类「{category}」不是支出分类，无法更新预算。"
    else:
        db.execute(
            "INSERT INTO categories (user_id, name, type) VALUES (?, ?, ?)",
            (user_id, category, CATEGORY_EXPENSE)
        )

    db.execute(
        "UPDATE budgets SET amount = ?, cycle = ? WHERE category = ? AND user_id = ?",
        (float(amount), cycle, category, user_id)
    )
    db.commit()

    return f"✅ 已更新「{category}」的预算为 ¥{amount}/{cycle}。别忘了定期检查哦！"


def delete_budget(user_id: int, params: dict[str, Any]) -> str:
    category = params.get(PARAM_CATEGORY)
    month = params.get(PARAM_MONTH) or datetime.now().strftime('%Y-%m')
    if not category:
        return "⚠️ 删除预算失败，缺少分类名称"
    db = get_db()
    result = db.execute(
        "DELETE FROM budgets WHERE user_id = ? AND category = ? AND month = ?",
        (user_id, category, month)
    )
    db.commit()
    if result.rowcount == 0:
        return f"⚠️ 未找到「{category}」{month} 的预算记录"
    return f"✅ 已删除「{category}」{month} 的预算。"


def analyze_spend(user_id: int, params: dict[str, Any]) -> str:
    """财务分析报告 — 使用合并查询优化（4→2 次数据库往返）"""
    db = get_db()
    month = params.get(PARAM_MONTH) or datetime.now().strftime('%Y-%m')

    reply = f"📊「{month}」财务分析报告：\n"

    # 合并查询：一次获取月度和总体支出数据
    spend_rows = db.execute(
        """
        SELECT category,
               SUM(amount) as overall_total,
               SUM(CASE WHEN strftime('%Y-%m', date) = ? THEN amount ELSE 0 END) as monthly_total
        FROM records WHERE user_id = ?
        GROUP BY category
        ORDER BY overall_total DESC
        LIMIT 10
        """,
        (month, user_id)
    ).fetchall()

    # 合并查询：一次获取月度和总体收入数据
    income_rows = db.execute(
        """
        SELECT category,
               SUM(amount) as overall_total,
               SUM(CASE WHEN strftime('%Y-%m', date) = ? THEN amount ELSE 0 END) as monthly_total
        FROM income WHERE user_id = ?
        GROUP BY category
        ORDER BY overall_total DESC
        LIMIT 10
        """,
        (month, user_id)
    ).fetchall()

    # === 支出分析输出 ===
    monthly_spend = [(r['category'], r['monthly_total']) for r in spend_rows if r['monthly_total'] > 0]
    monthly_spend.sort(key=lambda x: x[1], reverse=True)
    overall_spend = [(r['category'], r['overall_total']) for r in spend_rows if r['overall_total'] > 0]

    reply += "\n💸 本月支出排行：\n"
    if monthly_spend:
        for cat, total in monthly_spend[:5]:
            reply += f"👉 分类「{cat}」共支出 ¥{total:.2f}\n"
    else:
        reply += "暂无支出记录。\n"

    reply += "\n📌 总体支出排行：\n"
    if overall_spend:
        for cat, total in overall_spend[:5]:
            reply += f"📌 分类「{cat}」累计支出 ¥{total:.2f}\n"
    else:
        reply += "暂无历史支出数据。\n"

    # === 收入分析输出 ===
    monthly_income = [(r['category'], r['monthly_total']) for r in income_rows if r['monthly_total'] > 0]
    monthly_income.sort(key=lambda x: x[1], reverse=True)
    overall_income = [(r['category'], r['overall_total']) for r in income_rows if r['overall_total'] > 0]

    reply += "\n💰 本月收入来源排行：\n"
    if monthly_income:
        for cat, total in monthly_income[:5]:
            reply += f"✅ 来源「{cat}」共收入 ¥{total:.2f}\n"
    else:
        reply += "暂无收入记录。\n"

    reply += "\n📈 总体收入来源排行：\n"
    if overall_income:
        for cat, total in overall_income[:5]:
            reply += f"📈 来源「{cat}」累计收入 ¥{total:.2f}\n"
    else:
        reply += "暂无历史收入数据。\n"

    # ── 环比上月对比 ──
    year, mon = int(month[:4]), int(month[5:7])
    prev_month = f"{year - 1}-12" if mon == 1 else f"{year}-{mon - 1:02d}"

    prev_spend = float(db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM records WHERE strftime('%Y-%m', date) = ? AND user_id = ?",
        (prev_month, user_id),
    ).fetchone()[0])
    prev_income = float(db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM income WHERE strftime('%Y-%m', date) = ? AND user_id = ?",
        (prev_month, user_id),
    ).fetchone()[0])

    cur_spend = sum(r["monthly_total"] for r in spend_rows)
    cur_income = sum(r["monthly_total"] for r in income_rows)

    def _arrow(cur: float, prev: float) -> str:
        if prev == 0:
            return "（上月无数据）"
        pct = (cur - prev) / prev * 100
        arrow = "↑" if pct > 0 else "↓"
        return f"{arrow} {abs(pct):.1f}%（上月 ¥{prev:.2f}）"

    reply += f"\n📊 **环比上月（{prev_month}）**\n"
    reply += f"  支出：¥{cur_spend:.2f} {_arrow(cur_spend, prev_spend)}\n"
    reply += f"  收入：¥{cur_income:.2f} {_arrow(cur_income, prev_income)}\n"

    reply += "\n📌 建议：保持合理收支平衡，做好财务规划 👍"
    return reply


def add_category(user_id: int, params: dict[str, Any]) -> str:
    db = get_db()
    category = params.get(PARAM_CATEGORY, "").strip()
    category_type = params.get("类型", CATEGORY_EXPENSE).strip()

    if not category:
        return "⚠️ 分类名不能为空"
    if category_type not in (CATEGORY_EXPENSE, CATEGORY_INCOME):
        return "⚠️ 分类类型无效，应为「支出」或「收入」"

    row = db.execute(
        "SELECT type FROM categories WHERE name = ? AND user_id = ?",
        (category, user_id)
    ).fetchone()
    if row:
        if row["type"] == category_type:
            return f"⚠️ 分类「{category}」已存在，无需重复添加。"
        else:
            return f"⚠️ 分类「{category}」已存在，类型为「{row['type']}」，与当前设置不一致，请更换名称或删除原分类。"

    db.execute(
        "INSERT INTO categories (user_id, name, type) VALUES (?, ?, ?)",
        (user_id, category, category_type)
    )
    db.commit()
    return f"✅ 分类「{category}」（{category_type}）添加成功，快来使用吧！"


def delete_category(user_id: int, params: dict[str, Any]) -> str:
    db = get_db()
    category = params.get(PARAM_CATEGORY, "").strip()
    if not category:
        return "⚠️ 分类名不能为空"

    row = db.execute(
        "SELECT type FROM categories WHERE name = ? AND user_id = ?",
        (category, user_id)
    ).fetchone()
    if not row:
        return f"⚠️ 分类「{category}」不存在，无法删除。"

    category_type = row['type']

    if category_type == CATEGORY_EXPENSE:
        db.execute("DELETE FROM records WHERE category = ? AND user_id = ?", (category, user_id))
        db.execute("DELETE FROM budgets WHERE category = ? AND user_id = ?", (category, user_id))
    elif category_type == CATEGORY_INCOME:
        db.execute("DELETE FROM income WHERE category = ? AND user_id = ?", (category, user_id))

    db.execute("DELETE FROM categories WHERE name = ? AND user_id = ?", (category, user_id))
    db.commit()

    return f"✅ 已彻底删除分类「{category}」（{category_type}）及其相关记录，清理完毕！"


def budget_remain(user_id: int, params: dict[str, Any]) -> str:
    category = params.get(PARAM_CATEGORY)
    month = params.get(PARAM_MONTH) or datetime.now().strftime("%Y-%m")

    db = get_db()

    cursor = db.execute(
        """
        SELECT b.category, b.amount
        FROM budgets b
        JOIN categories c ON b.category = c.name AND c.user_id = b.user_id
        WHERE b.month = ? AND b.user_id = ? AND c.type = ?
    """,
        (month, user_id, CATEGORY_EXPENSE)
    )
    budget_map = {row['category']: float(row['amount']) for row in cursor.fetchall()}

    cursor = db.execute(
        """
        SELECT category, SUM(amount) as total
        FROM records
        WHERE strftime('%Y-%m', date) = ? AND user_id = ?
        GROUP BY category
    """,
        (month, user_id)
    )
    spend_map = {row['category']: float(row['total']) for row in cursor.fetchall()}

    if category:
        if category not in budget_map:
            return f"❌ 没有找到分类「{category}」在「{month}」的预算信息，或该分类不是支出类。"
        spent = spend_map.get(category, 0)
        remaining = budget_map[category] - spent
        return f"📊 分类「{category}」在 {month} 的预算为 ¥{budget_map[category]}，已支出 ¥{spent}，剩余 ¥{remaining:.2f}。"
    else:
        reply = f"📊 {month} 各支出分类预算情况：\n"
        for cat in budget_map:
            spent = spend_map.get(cat, 0)
            remaining = budget_map[cat] - spent
            reply += f"- {cat}：预算 ¥{budget_map[cat]}，已支出 ¥{spent}，剩余 ¥{remaining:.2f}\n"
        return reply


def call_deepseek_budget_advice(user_id: int, total_budget: float | None = None, llm: dict[str, Any] | None = None) -> str:
    from services.llm import call_llm_budget_advice

    llm = llm or {}
    logger.info("开始分配预算")

    db = get_db()
    today = datetime.now()
    if today.month == 1:
        last_month = f"{today.year - 1}-12"
    else:
        last_month = f"{today.year}-{today.month - 1:02d}"

    cursor = db.execute("""
        SELECT category, SUM(amount) as total
        FROM records
        WHERE user_id = ? AND strftime('%Y-%m', date) = ?
          AND category IN (
              SELECT name FROM categories WHERE type = ? AND user_id = ?
          )
        GROUP BY category
        ORDER BY total DESC
        LIMIT 5
    """, (user_id, last_month, CATEGORY_EXPENSE, user_id))

    summary_data = [
        {"category": row["category"], "total": round(float(row["total"]), 2),
         "average": round(float(row["total"]), 2)}
        for row in cursor.fetchall()
    ]

    if not summary_data:
        raise RuntimeError(f"上月（{last_month}）暂无消费记录，无法生成预算推荐")

    history_json = json.dumps(summary_data, ensure_ascii=False)

    logger.debug("上月（%s）Top 5 消费分类：%s", last_month, summary_data)
    logger.debug("设定总预算：%s", total_budget)

    if total_budget:
        budget_instruction = (
            f"你是一个智能财务顾问，用户设定了本月总预算为 {total_budget} 元。\n"
            f"以下是用户上月（{last_month}）消费最多的 5 个分类，请为这些分类分配合理的月预算。\n"
            "⚠️ 要求如下：\n"
            f"1. 所有分类预算总和必须严格等于 {total_budget} 元；\n"
            "2. 不得遗漏任何分类；\n"
            "3. 输出前请进行总额加和验证，确保不多不少刚好为总预算；\n"
            "4. 每个类别的预算值必须为整数！\n"
            "5. 输出结构化格式，不添加任何自然语言描述。\n"
        )
    else:
        budget_instruction = (
            "你是一个智能财务顾问，请根据用户上月消费情况，为以下分类生成合理的月预算建议。\n"
            "不限制预算总额，但应体现实际消费趋势。\n"
            "输出结构化格式，不添加自然语言描述。\n"
        )

    format_instruction = (
        "输出格式如下（每个分类占用两行）：\n"
        "分类：<分类名>\n"
        "建议预算：<预算金额>\n"
        "单位为元，金额保留一位小数。\n"
    )

    prompt = (
        budget_instruction +
        format_instruction +
        f"\n用户上月（{last_month}）Top 5 消费分类如下（JSON 列表，每项包含 category 和 total）：\n" +
        history_json
    )

    return call_llm_budget_advice(prompt, llm)


def suggest_budgets(user_id: int, params: dict[str, Any] | None = None, llm: dict[str, Any] | None = None) -> str:
    db = get_db()
    cursor = db.execute(
        "SELECT category, amount, date FROM records WHERE user_id = ?",
        (user_id,)
    )
    records = [dict(row) for row in cursor.fetchall()]
    if not records:
        return "📊 暂无支出记录，无法生成预算建议。"

    total = float(params.get("总预算", 0)) if params and "总预算" in params else None
    try:
        llm_reply = call_deepseek_budget_advice(user_id, total, llm)
    except RuntimeError as e:
        return f"⚠️ 智能预算推荐暂时不可用，请稍后再试。（{e}）"
    logger.debug("LLM 预算建议回复：%s", llm_reply)
    llm_logger.info("LLM：%s", llm_reply)

    pattern = r"分类：(.+?)\n建议预算：([\d.]+)"
    matches = re.findall(pattern, llm_reply)

    if not matches:
        return "⚠️ 无法解析 LLM 返回的建议格式"

    for category, budget in matches:
        category = category.strip()
        budget_val = float(budget)

        row = db.execute(
            "SELECT type FROM categories WHERE name = ? AND user_id = ?",
            (category, user_id)
        ).fetchone()
        if row:
            if row['type'] != CATEGORY_EXPENSE:
                continue
        else:
            db.execute(
                "INSERT INTO categories (user_id, name, type) VALUES (?, ?, ?)",
                (user_id, category, CATEGORY_EXPENSE)
            )

        db.execute(
            """
            INSERT OR REPLACE INTO budgets (user_id, category, amount, cycle, month)
            VALUES (?, ?, ?, ?, ?)
        """,
            (user_id, category, budget_val, "月", datetime.now().strftime("%Y-%m"))
        )

    db.commit()
    return "✅ 已根据智能分析更新预算设置：\n" + llm_reply


def search_records(user_id: int, params: dict[str, Any]) -> str:
    """列出支出明细（含ID），供 LLM 先查看再决定删除哪条"""
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
    """按记录ID删除一条支出记录"""
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


def delete_income(user_id: int, params: dict[str, Any]) -> str:
    """按记录ID删除一条收入记录"""
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


def query_income(user_id: int, params: dict[str, Any]) -> str:
    db = get_db()
    category = params.get(PARAM_CATEGORY, "").strip()
    time_range = params.get("时间范围", "").strip()
    show_all = params.get("全部", "") == "是"

    if show_all:
        cursor = db.execute(
            "SELECT * FROM income WHERE user_id = ? ORDER BY date DESC",
            (user_id,)
        )
        results = [dict(row) for row in cursor.fetchall()]
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

    cursor = db.execute(query, tuple(args))
    row = cursor.fetchone()
    total = float(row["total"] or 0)

    scope = ""
    if time_range:
        scope += f"{time_range} "
    if category:
        scope += f"来源「{category}」的"
    else:
        scope += "总"

    return f"💰 {scope}收入为 ¥{total:.2f}"


# ===== 投资模块（供 LLM 工具调用使用的中文键入口） =====

_INVEST_TYPES = {"stock", "fund", "bond", "cash", "crypto", "realestate", "other"}


def invest_add_asset(user_id: int, params: dict[str, Any]) -> str:
    name = (params.get("名称") or "").strip()
    atype = (params.get("类型") or "other").strip()
    if not name:
        return "⚠️ 请提供资产名称"
    if atype not in _INVEST_TYPES:
        return f"⚠️ 资产类型「{atype}」无效，支持：{'/'.join(sorted(_INVEST_TYPES))}"
    try:
        holdings = float(params.get("数量", 0) or 0)
        cost_basis = float(params.get("成本", 0) or 0)
        current_value = float(params.get("现值", 0) or 0)
    except (TypeError, ValueError):
        return "⚠️ 数量/成本/现值必须是数字"

    db = get_db()
    now = datetime.utcnow().isoformat(timespec="seconds")
    db.execute(
        "INSERT INTO assets (user_id, name, type, symbol, holdings, cost_basis, "
        "current_value, currency, notes, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'CNY', ?, ?, ?)",
        (user_id, name, atype, (params.get("代码") or "").strip() or None,
         holdings, cost_basis, current_value,
         (params.get("备注") or "").strip() or None, now, now),
    )
    db.commit()
    invalidate_user(user_id)
    return f"✅ 已登记资产「{name}」（{atype}），当前市值 ¥{current_value:.2f}"


def invest_update_value(user_id: int, params: dict[str, Any]) -> str:
    name = (params.get("名称") or "").strip()
    if not name:
        return "⚠️ 请提供资产名称"
    try:
        current_value = float(params.get("现值", 0) or 0)
    except (TypeError, ValueError):
        return "⚠️ 现值必须是数字"
    db = get_db()
    res = db.execute(
        "UPDATE assets SET current_value = ?, updated_at = ? WHERE user_id = ? AND name = ?",
        (current_value, datetime.utcnow().isoformat(timespec="seconds"), user_id, name),
    )
    db.commit()
    invalidate_user(user_id)
    if res.rowcount == 0:
        return f"⚠️ 未找到名为「{name}」的资产"
    return f"✅ 已更新「{name}」现值为 ¥{current_value:.2f}"


def invest_add_goal(user_id: int, params: dict[str, Any]) -> str:
    name = (params.get("名称") or "").strip()
    if not name:
        return "⚠️ 请提供目标名称"
    try:
        target = float(params.get("目标金额", 0) or 0)
    except (TypeError, ValueError):
        return "⚠️ 目标金额必须是数字"
    if target <= 0:
        return "⚠️ 目标金额需大于 0"
    db = get_db()
    now = datetime.utcnow().isoformat(timespec="seconds")
    db.execute(
        "INSERT INTO financial_goals (user_id, name, target_amount, deadline, "
        "current_progress, priority, note, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, name, target,
         (params.get("截止日期") or "").strip() or None,
         float(params.get("已完成", 0) or 0),
         int(params.get("优先级", 3) or 3),
         (params.get("备注") or "").strip() or None,
         now, now),
    )
    db.commit()
    deadline_str = f"，截止 {params.get('截止日期')}" if params.get("截止日期") else ""
    return f"✅ 已创建理财目标「{name}」目标金额 ¥{target:.2f}{deadline_str}"


def invest_portfolio_summary(user_id: int, params: dict[str, Any] | None = None) -> str:
    from services.portfolio import compute_allocation, compute_return
    db = get_db()
    rows = db.execute(
        "SELECT name, type, current_value, cost_basis FROM assets WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    if not rows:
        return "📊 暂无资产记录，先录入几项资产再回来分析吧。"
    assets = [dict(r) for r in rows]
    allo = compute_allocation(assets)
    ret = compute_return(assets)
    lines = [f"📊 投资组合总览：总市值 ¥{allo['total_value']:.2f}，累计回报 {ret['return_pct']:.2f}%"]
    lines.append("类型分布：")
    for row in allo["by_type"]:
        lines.append(f"  {row['type']}：¥{row['value']:.2f}（{row['pct']:.1f}%）")
    return "\n".join(lines)


def invest_analyze_portfolio(user_id: int, params: dict[str, Any] | None = None, llm: dict | None = None) -> str:
    """生成自然语言的投资组合诊断（调用 LLM）。"""
    from services.portfolio import compute_allocation, compute_drift, compute_return
    from services.llm import call_llm_portfolio_advice
    db = get_db()
    rows = db.execute(
        "SELECT name, type, current_value, cost_basis FROM assets WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    if not rows:
        return "📊 暂无资产记录，先录入几项资产再回来分析吧。"
    assets = [dict(r) for r in rows]
    allocation = compute_allocation(assets)
    returns = compute_return(assets)
    risk_row = db.execute(
        "SELECT level FROM risk_profiles WHERE user_id = ?", (user_id,),
    ).fetchone()
    risk_level = risk_row["level"] if risk_row else None
    drift = compute_drift(allocation, risk_level=risk_level)
    return call_llm_portfolio_advice(allocation, drift, returns, risk_level, llm=llm)


def category_sum(user_id: int, params: dict[str, Any]) -> str:
    category = params.get(PARAM_CATEGORY)
    start_date = params.get("开始时间")
    end_date = params.get("结束时间")

    db = get_db()
    cur = db.cursor()
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

    cur.execute(query, args)
    total = cur.fetchone()[0] or 0.0

    scope = f"{start_date} 至 {end_date}" if start_date and end_date else "所选范围内"
    if category:
        return f"📊 你在 {scope} 的「{category}」支出为 ¥{total:.2f}"
    else:
        return f"📊 你在 {scope} 的总支出为 ¥{total:.2f}"
