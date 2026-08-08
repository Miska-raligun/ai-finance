"""分类管理：add_category / delete_category。"""
from __future__ import annotations

from typing import Any

from constants import CATEGORY_EXPENSE, CATEGORY_INCOME, PARAM_CATEGORY
from db import get_db


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
        return (f"⚠️ 分类「{category}」已存在，类型为「{row['type']}」，"
                "与当前设置不一致，请更换名称或删除原分类。")

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
