"""预算管理：set / update / delete / remain / suggest（含 LLM 推荐）。"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from constants import (
    CATEGORY_EXPENSE,
    PARAM_AMOUNT, PARAM_CATEGORY, PARAM_MONTH,
)
from db import get_db

from ._common import cur_month, prev_month_of

logger = logging.getLogger(__name__)
llm_logger = logging.getLogger("llm_budget_suggest")


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
        "INSERT OR REPLACE INTO budgets (user_id, category, amount, cycle, month) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, category, float(amount), cycle, cur_month())
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
    month = params.get(PARAM_MONTH) or cur_month()
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


def budget_remain(user_id: int, params: dict[str, Any]) -> str:
    category = params.get(PARAM_CATEGORY)
    month = params.get(PARAM_MONTH) or cur_month()

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

    reply = f"📊 {month} 各支出分类预算情况：\n"
    for cat in budget_map:
        spent = spend_map.get(cat, 0)
        remaining = budget_map[cat] - spent
        reply += f"- {cat}：预算 ¥{budget_map[cat]}，已支出 ¥{spent}，剩余 ¥{remaining:.2f}\n"
    return reply


def call_deepseek_budget_advice(
    user_id: int,
    total_budget: float | None = None,
    llm: dict[str, Any] | None = None,
) -> str:
    from services.llm import call_llm_budget_advice

    llm = llm or {}
    logger.info("开始分配预算")

    db = get_db()
    last_month = prev_month_of(cur_month())

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


def suggest_budgets(
    user_id: int,
    params: dict[str, Any] | None = None,
    llm: dict[str, Any] | None = None,
) -> str:
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
            (user_id, category, budget_val, "月", cur_month())
        )

    db.commit()
    return "✅ 已根据智能分析更新预算设置：\n" + llm_reply
