from db import get_db
from datetime import datetime
import logging

llm_logger = logging.getLogger("llm_budget_suggest")
llm_logger.setLevel(logging.INFO)
if not llm_logger.handlers:
    handler = logging.FileHandler("llm_budget_suggest.log", encoding="utf-8")
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    llm_logger.addHandler(handler)
    
current_month = datetime.now().strftime("%Y-%m")

def add_record(user_id, params):
    db = get_db()
    category = params.get("分类", "").strip()
    note = params.get("备注", "").strip()
    amount = float(params.get("金额", 0))

    date = params.get("时间", "").strip()
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    month = date[:7]
    year = date[:4]

    if not category or not amount:
        return "⚠️ 分类和金额不能为空"

    # ✅ 查询分类类型是否为“收入”，不允许误用
    row = db.execute(
        "SELECT type FROM categories WHERE name = ? AND user_id = ?",
        (category, user_id)
    ).fetchone()
    if row:
        if row['type'] == '收入':
            return f"⚠️ 分类「{category}」已被设为收入来源，不能作为支出使用，请更换分类名。"
    else:
        # ✅ 新增分类并标记为“支出”
        db.execute("INSERT INTO categories (user_id, name, type) VALUES (?, ?, ?)", (user_id, category, '支出'))

    # ✅ 插入支出记录
    db.execute(
        "INSERT INTO records (user_id, category, amount, note, date, month, year) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, category, amount, note, date, month, year)
    )
    db.commit()

    return f"✅ 成功记录一笔消费：你在「{category}」方面支出了 ¥{amount}，备注为「{note}」，日期为 {date}。"

def add_income(user_id, params):
    db = get_db()
    category = params.get("分类", "").strip()
    note = params.get("备注", "").strip()
    amount = float(params.get("金额", 0))

    date = params.get("时间", "").strip()
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    month = date[:7]
    year = date[:4]

    if not category or not amount:
        return "⚠️ 收入的来源和金额不能为空"

    # ✅ 检查该收入来源是否已存在为“支出”分类
    row = db.execute(
        "SELECT type FROM categories WHERE name = ? AND user_id = ?",
        (category, user_id)
    ).fetchone()
    if row:
        if row['type'] == '支出':
            return f"⚠️ 「{category}」已作为支出分类存在，不能记录为收入来源，请更换名称。"
    else:
        # ✅ 新增收入来源分类
        db.execute(
            "INSERT INTO categories (user_id, name, type) VALUES (?, ?, ?)",
            (user_id, category, '收入')
        )

    # ✅ 插入收入记录
    db.execute(
        "INSERT INTO income (user_id, category, amount, note, date, month, year) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, category, amount, note, date, month, year)
    )
    db.commit()

    return f"✅ 成功记录一笔收入：你从「{category}」获得了 ¥{amount}，备注为「{note}」，日期为 {date}。"

def set_budget(user_id, params):
    print("🧠 LLM 预算参数:", params)

    category = params.get("分类")
    amount = params.get("金额") or params.get("预算")
    cycle = params.get("周期", "月")

    if not category or amount is None:
        return "⚠️ 设置预算失败，缺少分类或金额"

    db = get_db()

    # ✅ 查询分类是否存在，检查类型
    row = db.execute(
        "SELECT type FROM categories WHERE name = ? AND user_id = ?",
        (category, user_id)
    ).fetchone()
    if row:
        if row['type'] != '支出':
            return f"⚠️ 分类「{category}」不是支出分类，无法设置预算。"
    else:
        # ✅ 如果不存在则创建为支出分类
        db.execute(
            "INSERT INTO categories (user_id, name, type) VALUES (?, ?, ?)",
            (user_id, category, '支出')
        )

    # ✅ 设置预算（默认使用当前月）
    db.execute(
        "INSERT OR REPLACE INTO budgets (user_id, category, amount, cycle, month) VALUES (?, ?, ?, ?, ?)",
        (user_id, category, float(amount), cycle, current_month)
    )
    db.commit()

    return f"✅ 已为「{category}」设置 {cycle} 预算 ¥{amount}。理性消费，快乐生活！"

def update_budget(user_id, params):
    category = params.get("分类")
    amount = params.get("金额") or params.get("预算")
    cycle = params.get("周期", "月")

    if not category or amount is None:
        return "⚠️ 更新预算失败，缺少分类或金额"

    db = get_db()

    # ✅ 检查分类是否为支出类型
    row = db.execute(
        "SELECT type FROM categories WHERE name = ? AND user_id = ?",
        (category, user_id)
    ).fetchone()
    if row:
        if row['type'] != '支出':
            return f"⚠️ 分类「{category}」不是支出分类，无法更新预算。"
    else:
        # ✅ 若不存在则创建为支出分类
        db.execute(
            "INSERT INTO categories (user_id, name, type) VALUES (?, ?, ?)",
            (user_id, category, '支出')
        )

    # ✅ 更新预算记录
    db.execute(
        "UPDATE budgets SET amount = ?, cycle = ? WHERE category = ? AND user_id = ?",
        (float(amount), cycle, category, user_id)
    )
    db.commit()

    return f"✅ 已更新「{category}」的预算为 ¥{amount}/{cycle}。别忘了定期检查哦！"

def analyze_spend(user_id, params):
    db = get_db()
    month = params.get("月份") or datetime.now().strftime('%Y-%m')

    reply = f"📊「{month}」财务分析报告：\n"

    # ✅ 本月支出排行
    cursor = db.execute(
        """
        SELECT category, SUM(amount) as total
        FROM records
        WHERE month = ? AND user_id = ?
        GROUP BY category
        ORDER BY total DESC
        LIMIT 5
    """,
        (month, user_id)
    )
    monthly_spend = cursor.fetchall()

    # ✅ 历史总支出排行
    cursor = db.execute(
        """
        SELECT category, SUM(amount) as total
        FROM records
        WHERE user_id = ?
        GROUP BY category
        ORDER BY total DESC
        LIMIT 5
    """,
        (user_id,)
    )
    overall_spend = cursor.fetchall()

    # ✅ 本月收入排行
    cursor = db.execute(
        """
        SELECT category, SUM(amount) as total
        FROM income
        WHERE month = ? AND user_id = ?
        GROUP BY category
        ORDER BY total DESC
        LIMIT 5
    """,
        (month, user_id)
    )
    monthly_income = cursor.fetchall()

    # ✅ 历史总收入排行
    cursor = db.execute(
        """
        SELECT category, SUM(amount) as total
        FROM income
        WHERE user_id = ?
        GROUP BY category
        ORDER BY total DESC
        LIMIT 5
    """,
        (user_id,)
    )
    overall_income = cursor.fetchall()

    # === 支出分析输出 ===
    reply += "\n💸 本月支出排行：\n"
    if monthly_spend:
        for row in monthly_spend:
            reply += f"👉 分类「{row['category']}」共支出 ¥{row['total']:.2f}\n"
    else:
        reply += "暂无支出记录。\n"

    reply += "\n📌 总体支出排行：\n"
    if overall_spend:
        for row in overall_spend:
            reply += f"📌 分类「{row['category']}」累计支出 ¥{row['total']:.2f}\n"
    else:
        reply += "暂无历史支出数据。\n"

    # === 收入分析输出 ===
    reply += "\n💰 本月收入来源排行：\n"
    if monthly_income:
        for row in monthly_income:
            reply += f"✅ 来源「{row['category']}」共收入 ¥{row['total']:.2f}\n"
    else:
        reply += "暂无收入记录。\n"

    reply += "\n📈 总体收入来源排行：\n"
    if overall_income:
        for row in overall_income:
            reply += f"📈 来源「{row['category']}」累计收入 ¥{row['total']:.2f}\n"
    else:
        reply += "暂无历史收入数据。\n"

    reply += "\n📌 建议：保持合理收支平衡，做好财务规划 👍"
    return reply



def add_category(user_id, params):
    db = get_db()
    category = params.get("分类", "").strip()
    category_type = params.get("类型", "支出").strip()  # 默认为“支出”

    if not category:
        return "⚠️ 分类名不能为空"
    if category_type not in ("支出", "收入"):
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

    # ✅ 插入新分类
    db.execute(
        "INSERT INTO categories (user_id, name, type) VALUES (?, ?, ?)",
        (user_id, category, category_type)
    )
    db.commit()
    return f"✅ 分类「{category}」（{category_type}）添加成功，快来使用吧！"


def delete_category(user_id, params):
    db = get_db()
    category = params.get("分类", "").strip()
    if not category:
        return "⚠️ 分类名不能为空"

    row = db.execute(
        "SELECT type FROM categories WHERE name = ? AND user_id = ?",
        (category, user_id)
    ).fetchone()
    if not row:
        return f"⚠️ 分类「{category}」不存在，无法删除。"

    category_type = row['type']

    if category_type == '支出':
        db.execute("DELETE FROM records WHERE category = ? AND user_id = ?", (category, user_id))
        db.execute("DELETE FROM budgets WHERE category = ? AND user_id = ?", (category, user_id))
    elif category_type == '收入':
        db.execute("DELETE FROM income WHERE category = ? AND user_id = ?", (category, user_id))

    db.execute("DELETE FROM categories WHERE name = ? AND user_id = ?", (category, user_id))
    db.commit()

    return f"✅ 已彻底删除分类「{category}」（{category_type}）及其相关记录，清理完毕！"

def budget_remain(user_id, params):
    category = params.get("分类")
    month = params.get("月份") or datetime.now().strftime("%Y-%m")

    db = get_db()

    # ✅ 查询该月份的所有“支出”类预算信息
    cursor = db.execute(
        """
        SELECT b.category, b.amount
        FROM budgets b
        JOIN categories c ON b.category = c.name AND c.user_id = b.user_id
        WHERE b.month = ? AND b.user_id = ? AND c.type = '支出'
    """,
        (month, user_id)
    )
    budget_map = {row['category']: float(row['amount']) for row in cursor.fetchall()}

    # ✅ 查询该月份的所有“支出”记录
    cursor = db.execute(
        """
        SELECT category, SUM(amount) as total
        FROM records
        WHERE month = ? AND user_id = ?
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

import re
def call_deepseek_budget_advice(user_id, total_budget=None, llm=None):
    import os, requests, json

    llm = llm or {}

    print("开始分配预算")
    api_key = llm.get("apikey") or os.getenv("DEEPSEEK_API_KEY")
    url = llm.get("url") or "https://api.siliconflow.cn/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    from collections import defaultdict

    # ✅ 获取所有支出记录（历史所有月份）
    db = get_db()
    cursor = db.execute("""
        SELECT category, amount, month
        FROM records
        WHERE user_id = ? AND category IN (
            SELECT name FROM categories WHERE type = '支出' AND user_id = ?
        )
    """, (user_id, user_id))

    category_totals = defaultdict(float)
    category_months = defaultdict(set)

    for row in cursor.fetchall():
        category = row['category']
        amount = float(row['amount'])
        month = row['month']
        category_totals[category] += amount
        category_months[category].add(month)

    # ✅ 构造历史数据摘要
    summary_data = []
    for category in category_totals:
        total = round(category_totals[category], 2)
        months = len(category_months[category])
        average = round(total / months, 2) if months else 0
        summary_data.append({
            "category": category,
            "total": total,
            "average": average
        })

    history_json = json.dumps(summary_data, ensure_ascii=False)

    print("📊 分类历史消费汇总：", summary_data)
    print("🎯 设定总预算：", total_budget)
    print("🎯 用于预算分析的分类：", [item['category'] for item in summary_data])
    print("🎯 传给 LLM 的分类数量：", len(summary_data))

    if total_budget:
        budget_instruction = (
            f"你是一个智能财务顾问，用户设定了本月总预算为 {total_budget} 元。\n"
            "请根据用户历史消费记录中每个分类的支出情况，为所有出现过的分类分配一个合理的月预算。\n"
            "⚠️ 要求如下：\n"
            f"1. 所有分类预算总和必须严格等于 {total_budget} 元；\n"
            "2. 不得遗漏任何分类，至少涵盖所有出现在历史记录中的分类；\n"
            "3. 输出前请进行总额加和验证，确保不多不少刚好为总预算；\n"
            "4. 每个类别的预算值必须为整数！\n"
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
        "\n用户各分类的历史消费情况如下（JSON 列表，每项包含 category、total 和 average）：\n"+
        history_json
    )

    response = requests.post(url, headers=headers, json={
        "model": llm.get("model") or "Pro/deepseek-ai/DeepSeek-V3",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.5
    })

    print("📥 DeepSeek-r1 返回内容：", response.json())
    return response.json()["choices"][0]["message"]["content"]



def suggest_budgets(user_id, params=None, llm=None):
    db = get_db()
    cursor = db.execute(
        "SELECT category, amount, date FROM records WHERE user_id = ?",
        (user_id,)
    )
    records = [dict(row) for row in cursor.fetchall()]
    if not records:
        return "📊 暂无支出记录，无法生成预算建议。"

    total = float(params.get("总预算", 0)) if params and "总预算" in params else None
    llm_reply = call_deepseek_budget_advice(user_id, total, llm)
    print("🧠 LLM 预算建议回复：\n", llm_reply)
    llm_logger.info(f"LLM：{llm_reply}")

    # ✅ 解析 LLM 输出格式
    pattern = r"分类：(.+?)\n建议预算：([\d.]+)"
    matches = re.findall(pattern, llm_reply)

    if not matches:
        return "⚠️ 无法解析 LLM 返回的建议格式"

    for category, budget in matches:
        category = category.strip()
        budget = float(budget)

        # ✅ 确保分类存在且是支出类型
        row = db.execute(
            "SELECT type FROM categories WHERE name = ? AND user_id = ?",
            (category, user_id)
        ).fetchone()
        if row:
            if row['type'] != '支出':
                continue  # 跳过收入分类
        else:
            db.execute(
                "INSERT INTO categories (user_id, name, type) VALUES (?, ?, ?)",
                (user_id, category, '支出')
            )

        # ✅ 写入预算（无 year 字段）
        db.execute(
            """
            INSERT OR REPLACE INTO budgets (user_id, category, amount, cycle, month)
            VALUES (?, ?, ?, ?, ?)
        """,
            (user_id, category, budget, "月", current_month)
        )

    db.commit()
    return "✅ 已根据智能分析更新预算设置：\n" + llm_reply

def query_income(user_id, params):
    db = get_db()
    category = params.get("分类", "").strip()
    time_range = params.get("时间范围", "").strip()
    show_all = params.get("全部", "") == "是"

    results = []
    total = 0.0

    # ✅ 查询所有收入记录
    if show_all:
        cursor = db.execute(
            "SELECT * FROM income WHERE user_id = ? ORDER BY date DESC",
            (user_id,)
        )
        results = [dict(row) for row in cursor.fetchall()]
        total = sum(float(r["amount"]) for r in results)
        reply = f"📊 当前共记录 {len(results)} 笔收入，总计 ¥{total:.2f}\n"
        for r in results[:10]:  # 最多展示前10条
            reply += f"📌 {r['date']} - 来源「{r['category']}」收入 ¥{r['amount']}（备注：{r['note']}）\n"
        return reply + ("...（仅展示前10条）" if len(results) > 10 else "")

    # ✅ 聚合查询（可选时间范围 + 来源）
    query = "SELECT SUM(amount) AS total FROM income WHERE user_id = ?"
    args = [user_id]

    if time_range:
        if len(time_range) == 7:  # 2025-06（按月）
            query += " AND month = ?"
            args.append(time_range)
        elif len(time_range) == 4:  # 2025（按年）
            query += " AND year = ?"
            args.append(time_range)

    if category:
        query += " AND category = ?"
        args.append(category)

    cursor = db.execute(query, tuple(args))
    row = cursor.fetchone()
    total = float(row["total"] or 0)

    # 构造自然语言响应
    scope = ""
    if time_range:
        scope += f"{time_range} "
    if category:
        scope += f"来源「{category}」的"
    else:
        scope += "总"

    return f"💰 {scope}收入为 ¥{total:.2f}"

def category_sum(user_id, params):
    # 从 params 中提取分类和时间范围
    category = params.get("分类")
    start_date = params.get("开始时间")
    end_date = params.get("结束时间")

    db = get_db()
    cur = db.cursor()
    query = "SELECT SUM(amount) FROM records WHERE user_id = ?"
    args = [user_id]

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
        return f"📊 你在 {scope} 的“{category}”支出为 ¥{total:.2f}"
    else:
        return f"📊 你在 {scope} 的总支出为 ¥{total:.2f}"





