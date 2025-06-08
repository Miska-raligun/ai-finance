from db import get_db

def add_record(params):
    db = get_db()
    category = params.get("分类", "").strip()
    note = params.get("备注", "").strip()
    amount = float(params.get("金额", 0))
    date = params.get("时间", "").strip()

    if not category or not amount:
        return "⚠️ 分类和金额不能为空"

    db.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (category,))
    db.execute(
        "INSERT INTO records (category, note, amount, date) VALUES (?, ?, ?, ?)",
        (category, note, amount, date)
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
        "INSERT OR REPLACE INTO budgets (category, amount, cycle) VALUES (?, ?, ?)",
        (category, float(amount), cycle)
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
    cursor = db.execute("SELECT category, SUM(amount) as total FROM records GROUP BY category ORDER BY total DESC LIMIT 5")
    results = cursor.fetchall()
    if not results:
        return "📊 当前还没有支出记录呢，快去记录第一笔消费吧！"

    reply = "📊 本月消费分析如下：\n"
    for row in results:
        reply += f"👉 分类「{row['category']}」共消费 ¥{row['total']:.2f}\n"

    return reply + "\n💡 建议：检查是否有过度消费的项目，合理调整预算哦~"

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
