from flask import Flask, request, jsonify
from db import init_db, get_db
from handlers import *
from dotenv import load_dotenv
import os, requests
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)
init_db()
load_dotenv()  # 加载 .env 文件

handlers = {
    "add_record": add_record,
    "add_income": add_income,  # ✅ 新增
    "set_budget": set_budget,
    "update_budget": update_budget,
    "analyze_spend": analyze_spend,
    "add_category": add_category,
    "delete_category": delete_category,
    "budget_remain": budget_remain,
    "suggest_budgets": suggest_budgets,
    "query_income": query_income
}

# 意图别名映射
INTENT_ALIAS = {
    "记录支出": "add_record",
    "支出记录": "add_record",
    "add_record": "add_record"
}

def call_deepseek_intent(message):
    import os, requests

    today_str = datetime.now().strftime("%Y-%m-%d")
    api_key = os.getenv("DEEPSEEK_API_KEY")
    url = "https://api.siliconflow.cn/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    prompt = (
        f"今天是 {today_str}。\n"
        "你是一个智能财务助理。请根据用户输入生成结构化的意图（intent）和参数（params）。\n"
        "意图必须为：add_record, add_income, set_budget, update_budget, analyze_spend, add_category, delete_category, budget_remain, suggest_budgets, query_income。\n"
        "请结合“今天、昨天、上周、5月1日”等模糊表达推断具体日期，并提取出对应的月份（格式如 2025-06）。\n"
        "意图为 suggest_budgets 时，参数中务必使用“总预算”字段；\n"
        "意图为 add_record时，需提取：分类、金额、备注、时间、月份；\n"
        "意图为 add_income时，需提取：分类、金额、备注、时间、月份；\n"
        "意图为 query_income 时，参数可包含以下之一或组合：\n"
        "① 来源：如 工资、兼职（可选）\n"
        "② 时间范围：如 2025-06 或 2025（可选）\n"
        "③ 全部：是（表示查询所有收入记录）\n"
        "请严格使用以下结构化格式输出，不得添加自然语言解释或括号说明：\n"
        "意图：add_record\n"
        "参数：\n"
        "分类：餐饮\n"
        "金额：25\n"
        "备注：麦当劳\n"
        "时间：2025-06-08\n"
        "月份：2025-06"
    )

    payload = {
        "model": "Pro/deepseek-ai/DeepSeek-V3",
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": message}
        ]
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        data = res.json()
        print("📥 DeepSeek 返回内容：", data)  # 打印原始返回，方便调试

        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        elif "error" in data:
            print("❌ DeepSeek API 错误：", data["error"])
            return "意图：unknown\\n参数："
        else:
            print("❓ 未知格式响应：", data)
            return "意图：unknown\\n参数："

    except Exception as e:
        print("DeepSeek 调用失败:", e)
        return "意图：unknown\\n参数："

def call_deepseek_summary(user_msg, handler_result):
    import os, requests

    api_key = os.getenv("DEEPSEEK_API_KEY")
    url = "https://api.siliconflow.cn/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    summary_prompt = (
        "你是一个财务顾问，请根据用户的操作结果进行总结和建议。\n"
        "用户输入：{user_msg}\n"
        "系统执行结果：{handler_result}\n"
        "请用自然语言总结这次操作及执行结果，并提出简短合理的建议（50字以内）,不要添加不必要的格式化符号。\n"
        "当系统执行结果涉及具体数值时，必须保留全部数值，严禁省略！\n"
        "回复尽量人性化且风趣。\n"
        "不要做()括起来的额外回复。\n"
        "如果用户此次操作为本月消费分析请求，给出消费行为详细分析及评分，此时不限制回答字数，必须分别分析当月消费和总体消费，严禁混淆分析！"
    ).format(user_msg=user_msg, handler_result=handler_result)

    data = {
        "model": "Pro/deepseek-ai/DeepSeek-V3",
        "messages": [
            {"role": "system", "content": "你是一个善于总结和分析的财务顾问。"},
            {"role": "user", "content": summary_prompt}
        ]
    }

    response = requests.post(url, headers=headers, json=data)
    result = response.json()

    if "choices" in result:
        return result["choices"][0]["message"]["content"]
    elif "error" in result:
        print("❌ DeepSeek API error:", result["error"])
        return "❌ 分析失败：" + result["error"].get("message", "未知错误")
    else:
        print("❌ DeepSeek API unexpected response:", result)
        return "❌ 分析失败：LLM 响应格式异常"

def parse_response(text):
    lines = text.strip().split('\n')
    intent = ""
    params = {}
    mode = None
    for line in lines:
        if line.startswith("意图："):
            intent_raw = line.split("：", 1)[1].strip()
            intent = INTENT_ALIAS.get(intent_raw, intent_raw)
        elif line.startswith("参数："):
            mode = "param"
        elif "：" in line and mode == "param":
            k, v = line.split("：", 1)
            params[k.strip()] = v.strip()

    return intent, params

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_msg = data.get("message", "")

    llm_output = call_deepseek_intent(user_msg)
    print("🧠 LLM 原始结构化输出：", llm_output)

    intent, params = parse_response(llm_output)

    if intent in handlers:
        result = handlers[intent](params)
        print("📦 handler 执行结果：", result)

        if intent == "add_record":
            from db import get_db
            db = get_db()
            cursor = db.execute("SELECT * FROM records ORDER BY date DESC")
            print("📒 当前记录：")
            for row in cursor.fetchall():
                print(dict(row))

        if intent == "add_income":
            from db import get_db
            db = get_db()
            cursor = db.execute("SELECT * FROM income ORDER BY date DESC")
            print("📒 当前记录：")
            for row in cursor.fetchall():
                print(dict(row))
        # 用 LLM 进行总结生成自然语言
        reply = call_deepseek_summary(user_msg, result)
    else:
        reply = "⚠️ 暂不支持该操作"

    return jsonify({"reply": reply}) 

@app.route('/records')
def get_records():
    db = get_db()
    month = request.args.get("month")
    if month:
        cursor = db.execute("""
            SELECT *, strftime('%Y-%m', date) as month
            FROM records
            WHERE strftime('%Y-%m', date) = ?
            ORDER BY date DESC
        """, (month,))
    else:
        cursor = db.execute("""
            SELECT *, strftime('%Y-%m', date) as month
            FROM records
            ORDER BY date DESC
        """)
    results = [dict(row) for row in cursor.fetchall()]
    return jsonify(results)

@app.route('/income')
def get_income():
    db = get_db()
    month = request.args.get("month")

    if month:
        cursor = db.execute("""
            SELECT id, category, amount, note, date, month, year
            FROM income
            WHERE month = ?
            ORDER BY date DESC
        """, (month,))
    else:
        cursor = db.execute("""
            SELECT id, category, amount, note, date, month, year
            FROM income
            ORDER BY date DESC
        """)

    results = [dict(row) for row in cursor.fetchall()]

    # ✅ 防御式检查每条记录都有 date 字段
    for r in results:
        if "date" not in r or not r["date"]:
            r["date"] = r.get("month", "") + "-01"

    return jsonify(results)


@app.route("/categories", methods=["GET"])
def get_categories():
    db = get_db()
    category_type = request.args.get("type")

    type_map = {
        "income": "收入",
        "expense": "支出"
    }

    if category_type in type_map:
        cursor = db.execute(
            "SELECT * FROM categories WHERE type = ? ORDER BY name ASC",
            (type_map[category_type],)
        )
    else:
        cursor = db.execute("SELECT * FROM categories ORDER BY name ASC")

    results = [dict(row) for row in cursor.fetchall()]
    if not isinstance(results, list):
        return jsonify([])  # 🛡 确保一定返回数组
    return jsonify(results)


month = datetime.now().strftime("%Y-%m")
@app.route('/budgets')
def get_budgets():
    db = get_db()
    month = request.args.get('month')
    result = []

    if month:
        # ✅ 仅查指定月份支出类预算
        cursor = db.execute("""
            SELECT b.category, b.amount
            FROM budgets b
            JOIN categories c ON b.category = c.name
            WHERE b.month = ? AND c.type = '支出'
        """, (month,))
        budgets = cursor.fetchall()

        cursor = db.execute("""
            SELECT category, SUM(amount) as total
            FROM records
            WHERE strftime('%Y-%m', date) = ?
            GROUP BY category
        """, (month,))
        spend_map = {row['category']: row['total'] for row in cursor.fetchall()}

        for b in budgets:
            spent = spend_map.get(b['category'], 0)
            remaining = float(b['amount']) - float(spent)
            result.append({
                'category': b['category'],
                'amount': float(b['amount']),
                'remaining': round(remaining, 2),
                'month': month
            })

    else:
        # ✅ 查所有月份的支出类预算
        cursor = db.execute("""
            SELECT b.category, b.amount, b.month
            FROM budgets b
            JOIN categories c ON b.category = c.name
            WHERE c.type = '支出'
        """)
        all_budgets = cursor.fetchall()

        cursor = db.execute("""
            SELECT category, strftime('%Y-%m', date) as month, SUM(amount) as total
            FROM records
            GROUP BY category, month
        """)
        spend_map = {(row['category'], row['month']): row['total'] for row in cursor.fetchall()}

        for b in all_budgets:
            key = (b['category'], b['month'])
            spent = spend_map.get(key, 0)
            remaining = float(b['amount']) - float(spent)
            result.append({
                'category': b['category'],
                'amount': float(b['amount']),
                'remaining': round(remaining, 2),
                'month': b['month']
            })

    return jsonify(result)

@app.route("/categories", methods=["POST"])
def add_category_manual():
    data = request.get_json()
    name = data.get("name", "").strip()
    category_type = data.get("type", "支出").strip()

    if not name:
        return jsonify({"error": "缺少分类名称"}), 400
    if category_type not in ("支出", "收入"):
        return jsonify({"error": "分类类型必须是「支出」或「收入」"}), 400

    db = get_db()
    try:
        db.execute("INSERT INTO categories (name, type) VALUES (?, ?)", (name, category_type))
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route("/categories/<name>", methods=["DELETE"])
def delete_category_manual(name):
    db = get_db()

    # ✅ 获取分类类型
    row = db.execute("SELECT type FROM categories WHERE name = ?", (name,)).fetchone()
    if not row:
        return jsonify({"error": f"分类「{name}」不存在"}), 404

    category_type = row["type"]

    # ✅ 删除记录
    if category_type == "支出":
        db.execute("DELETE FROM records WHERE category = ?", (name,))
        db.execute("DELETE FROM budgets WHERE category = ?", (name,))
    elif category_type == "收入":
        db.execute("DELETE FROM income WHERE source = ?", (name,))

    # ✅ 删除分类本身
    db.execute("DELETE FROM categories WHERE name = ?", (name,))
    db.commit()

    return jsonify({"success": True})

@app.route("/budgets", methods=["POST"])
def set_budget_manual():
    data = request.get_json()
    category = data.get("category", "").strip()
    amount = float(data.get("amount", 0))
    cycle = data.get("cycle", "月")
    month = data.get("month") or datetime.now().strftime('%Y-%m')

    if not category:
        return jsonify({"error": "缺少分类名称"}), 400

    db = get_db()

    # ✅ 检查分类是否存在且为支出类型
    row = db.execute("SELECT type FROM categories WHERE name = ?", (category,)).fetchone()
    if not row:
        return jsonify({"error": f"分类「{category}」不存在"}), 400
    if row["type"] != "支出":
        return jsonify({"error": f"分类「{category}」不是支出类型，无法设置预算"}), 400

    # ✅ 写入预算
    db.execute("""
        INSERT OR REPLACE INTO budgets (category, amount, cycle, month)
        VALUES (?, ?, ?, ?)
    """, (category, amount, cycle, month))
    db.commit()
    return jsonify({"success": True})



@app.route("/stats/monthly", methods=["GET"])
def monthly_stats():
    db = get_db()

    # 支出统计
    spend_cursor = db.execute("""
        SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total
        FROM records
        GROUP BY month
    """)
    spend_data = {row['month']: float(row['total']) for row in spend_cursor.fetchall()}

    # 收入统计
    income_cursor = db.execute("""
        SELECT month, SUM(amount) AS total
        FROM income
        GROUP BY month
    """)
    income_data = {row['month']: float(row['total']) for row in income_cursor.fetchall()}

    # 合并所有月份
    all_months = sorted(set(spend_data.keys()) | set(income_data.keys()), reverse=True)

    result = []
    for m in all_months:
        result.append({
            "month": m,
            "支出": spend_data.get(m, 0.0),
            "收入": income_data.get(m, 0.0)
        })

    return jsonify(result)

@app.route("/stats/by-category", methods=["GET"])
def category_stats():
    db = get_db()
    month = request.args.get("month")
    year = request.args.get("year")

    if month:
        spend_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM records WHERE month = ? GROUP BY category",
            (month,),
        )
        income_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM income WHERE month = ? GROUP BY category",
            (month,),
        )
    elif year:
        spend_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM records WHERE year = ? GROUP BY category",
            (year,),
        )
        income_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM income WHERE year = ? GROUP BY category",
            (year,),
        )
    else:
        spend_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM records GROUP BY category"
        )
        income_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM income GROUP BY category"
        )

    income_result = [
        {"名称": row["name"], "金额": float(row["total"]), "类型": "收入"}
        for row in income_cursor.fetchall()
    ]
    spend_result = [
        {"名称": row["name"], "金额": float(row["total"]), "类型": "支出"}
        for row in spend_cursor.fetchall()
    ]
    return jsonify(spend_result + income_result)

@app.route("/stats/summary", methods=["GET"])
def summary_stats():
    db = get_db()
    month = request.args.get("month") or datetime.now().strftime("%Y-%m")

    # ✅ 查询该月总支出
    spend_cursor = db.execute("""
        SELECT SUM(amount) AS total
        FROM records
        WHERE month = ?
    """, (month,))
    spend_total = float(spend_cursor.fetchone()["total"] or 0.0)

    # ✅ 查询该月总收入
    income_cursor = db.execute("""
        SELECT SUM(amount) AS total
        FROM income
        WHERE month = ?
    """, (month,))
    income_total = float(income_cursor.fetchone()["total"] or 0.0)

    # ✅ 差额计算
    balance = income_total - spend_total

    return jsonify({
        "month": month,
        "总支出": round(spend_total, 2),
        "总收入": round(income_total, 2),
        "结余": round(balance, 2)
    })

@app.route("/stats/daily")
def daily_stats():
    db = get_db()
    month = request.args.get("month")
    if not month:
        return jsonify({"error": "缺少参数 month"}), 400

    # 支出
    spend_cursor = db.execute("""
        SELECT date, SUM(amount) AS total
        FROM records
        WHERE strftime('%Y-%m', date) = ?
        GROUP BY date
    """, (month,))
    spend_map = {row['date']: float(row['total']) for row in spend_cursor.fetchall()}

    # 收入
    income_cursor = db.execute("""
        SELECT date, SUM(amount) AS total
        FROM income
        WHERE strftime('%Y-%m', date) = ?
        GROUP BY date
    """, (month,))
    income_map = {row['date']: float(row['total']) for row in income_cursor.fetchall()}

    all_dates = sorted(set(spend_map) | set(income_map))
    result = []
    for d in all_dates:
        spend = spend_map.get(d, 0.0)
        income = income_map.get(d, 0.0)
        result.append({
            "date": d,
            "支出": spend,
            "收入": income,
            "结余": round(income - spend, 2)
        })

    return jsonify(result)
