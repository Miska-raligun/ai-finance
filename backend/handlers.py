from db import get_db
from datetime import datetime
current_month = datetime.now().strftime("%Y-%m")
def add_record(params):
    db = get_db()
    category = params.get("分类", "").strip()
    note = params.get("备注", "").strip()
    amount = float(params.get("金额", 0))

    date = params.get("时间", "").strip()
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")  # 如果 LLM 没返回时间字段，就使用当前时间

    month = date[:7]  # 只取前 7 位，如 2025-06
    if not category or not amount:
        return "⚠️ 分类和金额不能为空"

    db.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (category,))
    db.execute(
        "INSERT INTO records (category, amount, note, date, month) VALUES (?, ?, ?, ?, ?)",
        (category, amount, note, date, month)
    )
    db.commit()

    return f"✅ 成功记录一笔消费：你在「{category}」方面支出了 ¥{amount}，备注为「{note}」，日期为 {date}。"

def set_budget(params):
    print("🧠 LLM 预算参数:", params)

    category = params.get("分类")
    amount = params.get("金额") or params.get("预算")
    cycle = params.get("周期", "月")

    if not category or amount is None:
        return "⚠️ 设置预算失败，缺少分类或金额"

    db = get_db()
    db.execute("INSERT OR REPLACE INTO categories (name) VALUES (?)", (category,))
    db.execute(
        "INSERT OR REPLACE INTO budgets (category, amount, cycle, month) VALUES (?, ?, ?, ?)",
        (category, float(amount), cycle, current_month)
    )
    db.commit()

    return f"✅ 已为「{category}」设置 {cycle} 预算 ¥{amount}。理性消费，快乐生活！"

def update_budget(params):
    category = params.get("分类")
    amount = params.get("金额") or params.get("预算")
    cycle = params.get("周期", "月")

    if not category or amount is None:
        return "⚠️ 更新预算失败，缺少分类或金额"

    db = get_db()
    db.execute("INSERT OR REPLACE INTO categories (name) VALUES (?)", (category,))
    db.execute(
        "UPDATE budgets SET amount = ?, cycle = ? WHERE category = ?",
        (float(amount), cycle, category)
    )
    db.commit()

    return f"✅ 已更新「{category}」的预算为 ¥{amount}/{cycle}。别忘了定期检查哦！"


def analyze_spend(params):
    db = get_db()

    # ✅ 从 params 获取月份，格式如 "2025-06"，否则用当前月
    month = params.get("月份") or datetime.now().strftime('%Y-%m')

    # ✅ 查询本月支出排行
    cursor = db.execute("""
        SELECT category, SUM(amount) as total
        FROM records
        WHERE strftime('%Y-%m', date) = ?
        GROUP BY category
        ORDER BY total DESC
        LIMIT 5
    """, (month,))
    monthly = cursor.fetchall()

    # ✅ 查询总支出排行
    cursor = db.execute("""
        SELECT category, SUM(amount) as total
        FROM records
        GROUP BY category
        ORDER BY total DESC
        LIMIT 5
    """)
    overall = cursor.fetchall()

    # ✅ 构建回复
    reply = f"📅 「{month}」月消费分析：\n"
    if monthly:
        for row in monthly:
            reply += f"👉 分类「{row['category']}」共消费 ¥{row['total']:.2f}\n"
    else:
        reply += "暂无消费记录。\n"

    reply += "\n📊 总体消费排行：\n"
    if overall:
        for row in overall:
            reply += f"📌 分类「{row['category']}」累计消费 ¥{row['total']:.2f}\n"
    else:
        reply += "暂无历史数据。\n"

    reply += "\n💡 建议：关注消费趋势，优化大额支出结构哦~"
    return reply


def add_category(params):
    db = get_db()
    category = params.get("分类", "").strip()
    if not category:
        return "⚠️ 分类名不能为空"

    try:
        db.execute("INSERT INTO categories (name) VALUES (?)", (category,))
        db.commit()
        return f"✅ 分类「{category}」添加成功，快来使用吧！"
    except:
        return f"⚠️ 分类「{category}」已存在或无效。"

def delete_category(params):
    db = get_db()
    category = params.get("分类", "").strip()
    if not category:
        return "⚠️ 分类名不能为空"

    db.execute("DELETE FROM categories WHERE name = ?", (category,))
    db.execute("DELETE FROM budgets WHERE category = ?", (category,))
    db.execute("DELETE FROM records WHERE category = ?", (category,))
    db.commit()

    return f"✅ 已彻底删除分类「{category}」及其相关预算与记录，清理完毕！"

def budget_remain(params):
    category = params.get("分类")
    month = params.get("月份") or datetime.now().strftime("%Y-%m")

    db = get_db()
    # ✅ 筛选指定月份的预算
    cursor = db.execute("SELECT category, amount FROM budgets WHERE month = ?", (month,))
    budget_map = {row['category']: float(row['amount']) for row in cursor.fetchall()}

    # ✅ 筛选指定月份的支出记录
    cursor = db.execute("SELECT category, SUM(amount) as total FROM records WHERE month = ? GROUP BY category", (month,))
    spend_map = {row['category']: float(row['total']) for row in cursor.fetchall()}

    if category:
        if category not in budget_map:
            return f"❌ 没有找到分类「{category}」在「{month}」的预算信息。"
        spent = spend_map.get(category, 0)
        remaining = budget_map[category] - spent
        return f"📊 分类「{category}」在 {month} 的预算为 ¥{budget_map[category]}，已支出 ¥{spent}，剩余 ¥{remaining:.2f}。"
    else:
        reply = f"📊 {month} 各分类预算情况：\n"
        for cat in budget_map:
            spent = spend_map.get(cat, 0)
            remaining = budget_map[cat] - spent
            reply += f"- {cat}：预算 ¥{budget_map[cat]}，已支出 ¥{spent}，剩余 ¥{remaining:.2f}\n"
        return reply

import re
def call_deepseek_budget_advice(records, total_budget=None):
    import os, requests, json

    print("开始分配预算")
    api_key = os.getenv("DEEPSEEK_API_KEY")
    url = "https://api.siliconflow.cn/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    history_json = json.dumps(records, ensure_ascii=False)
    print(total_budget)

    if total_budget:
        budget_instruction = (
            f"你是一个智能财务顾问，用户设定了本月总预算为 {total_budget} 元。\n"
            "请根据用户历史消费记录中每个分类的支出情况，为所有出现过的分类分配一个合理的月预算。\n"
            "⚠️ 要求如下：\n"
            f"1. 所有分类预算总和必须严格等于 {total_budget} 元；\n"
            "2. 不得遗漏任何分类，至少涵盖所有出现在历史记录中的分类；\n"
            "3. 输出前请进行总额加和验证，确保不多不少刚好为总预算；\n"
            "4. 每个类别的预算值必须为整数。\n"
            "5. 输出结构化格式，不添加任何自然语言描述。\n"
        )
    else:
        budget_instruction = (
            "你是一个智能财务顾问，请根据用户历史消费记录中每个分类的支出情况，为每个分类生成一个合理的月预算建议。\n"
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
        "\n用户历史记录如下（JSON 列表，每项包含 category, amount, date）：\n" +
        history_json
    )

    response = requests.post(url, headers=headers, json={
        "model": "Pro/deepseek-ai/DeepSeek-V3",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.5
    })

    print("📥 DeepSeek-r1 返回内容：", response.json())  # 打印原始返回，方便调试
    return response.json()["choices"][0]["message"]["content"]


def suggest_budgets(params=None):
    db = get_db()
    cursor = db.execute("SELECT category, amount, date FROM records")
    records = [dict(row) for row in cursor.fetchall()]
    if not records:
        return "📊 暂无记录，无法生成预算建议。"

    total = float(params.get("总预算", 0)) or None
    llm_reply = call_deepseek_budget_advice(records,total)
    print("🧠 LLM 预算建议回复：\n", llm_reply)

    # 解析 LLM 输出格式
    pattern = r"分类：(.+?)\n建议预算：([\d.]+)"
    matches = re.findall(pattern, llm_reply)

    if not matches:
        return "⚠️ 无法解析 LLM 返回的建议格式"

    for category, budget in matches:
        db.execute(
            "INSERT OR REPLACE INTO budgets (category, amount, cycle, month) VALUES (?, ?, ?, ?)",
            (category.strip(), float(budget), "月", current_month)
        )
    db.commit()

    return "✅ 已根据智能分析更新预算设置：\n" + llm_reply


