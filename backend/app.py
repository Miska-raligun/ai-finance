from flask import Flask, request, jsonify, g
from db import init_db, get_db
from handlers import *
from dotenv import load_dotenv
import os, requests, secrets, logging
#from flask_cors import CORS
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

app = Flask(__name__)
#CORS(app)
init_db()
load_dotenv()  # 加载 .env 文件

# 在内存中维护最近10条对话记录
chat_history = []  # [{"role": "user"/"assistant", "content": "..."}]

# ===== 简易用户认证 =====
tokens = {}

def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "")
        user_id = tokens.get(token)
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401
        g.user_id = user_id
        return f(*args, **kwargs)
    return wrapper


@app.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400

    db = get_db()
    cursor = db.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        return jsonify({"error": "用户名已存在"}), 400

    pw_hash = generate_password_hash(password)
    db.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, pw_hash))
    db.commit()
    return jsonify({"success": True})


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    db = get_db()
    row = db.execute("SELECT id, password FROM users WHERE username = ?", (username,)).fetchone()
    if not row or not check_password_hash(row["password"], password):
        return jsonify({"error": "用户名或密码错误"}), 400

    token = secrets.token_hex(16)
    tokens[token] = row["id"]
    return jsonify({"token": token})

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "")
    tokens.pop(token, None)
    return jsonify({"success": True})

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

def call_deepseek_intent(message, llm=None):
    import os, requests

    llm = llm or {}

    today_str = datetime.now().strftime("%Y-%m-%d")
    api_key = llm.get("apikey") or os.getenv("DEEPSEEK_API_KEY")
    url = llm.get("url") or "https://api.siliconflow.cn/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    prompt = (
        f"今天是 {today_str}。\n"
        "你是一个智能财务助理。请根据用户输入生成结构化的意图（intent）和参数（params）。\n"
        "意图必须为：add_record, add_income, set_budget, update_budget, analyze_spend, add_category, delete_category, budget_remain, suggest_budgets, query_income, chat。\n"
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
        "model": llm.get("model") or "Pro/deepseek-ai/DeepSeek-V3",
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

def call_deepseek_summary(user_msg, handler_result, llm=None):
    import os, requests

    llm = llm or {}

    api_key = llm.get("apikey") or os.getenv("DEEPSEEK_API_KEY")
    url = llm.get("url") or "https://api.siliconflow.cn/v1/chat/completions"
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
        "model": llm.get("model") or "Pro/deepseek-ai/DeepSeek-V3",
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

def call_deepseek_chat(history, llm=None):
    """当用户没有执行记账相关操作时，与其闲聊。"""
    api_key = (llm or {}).get("apikey") or os.getenv("DEEPSEEK_API_KEY")
    url = (llm or {}).get("url") or "https://api.siliconflow.cn/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    prompt = (
        "你是一个友好的记账助手，可以和用户闲聊，并在合适的时候提醒保持良好的记账习惯。\n"
        "回答控制在50字以内。"
    )

    messages = [{"role": "system", "content": prompt}] + history[-10:]

    data = {
        "model": (llm or {}).get("model") or "Pro/deepseek-ai/DeepSeek-V3",
        "messages": messages,
    }

    try:
        res = requests.post(url, headers=headers, json=data, timeout=10)
        result = res.json()
        if "choices" in result:
            return result["choices"][0]["message"]["content"]
        elif "error" in result:
            print("❌ DeepSeek chat error:", result["error"])
            return "⚠️ 暂时无法回复"
        else:
            print("❌ DeepSeek chat unexpected response:", result)
            return "⚠️ 暂时无法回复"
    except Exception as e:
        print("DeepSeek chat failed:", e)
        return "⚠️ 暂时无法回复"

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
@login_required
def chat():
    data = request.get_json()
    llm_cfg = data.get("llm") or {}
    user_msg = data.get("message", "")
    latest_msg = user_msg
    if isinstance(user_msg, str):
        latest_msg = user_msg.strip().split("\n")[-1]

    # 记录对话历史
    chat_history.append({"role": "user", "content": user_msg})
    if len(chat_history) > 10:
        del chat_history[:-10]

    print("最新消息: ",latest_msg)
    llm_output = call_deepseek_intent(latest_msg, llm_cfg)
    print("🧠 LLM 原始结构化输出：", llm_output)

    intent, params = parse_response(llm_output)

    if intent in handlers:
        if intent == "suggest_budgets":
            result = handlers[intent](g.user_id, params, llm_cfg)
        else:
            result = handlers[intent](g.user_id, params)
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
        reply = call_deepseek_summary(latest_msg, result, llm_cfg)
    else:
        # 如果未识别出意图，直接和用户闲聊几句
        print("llm输入:",chat_history)
        reply = call_deepseek_chat(chat_history, llm_cfg)

    # 记录 assistant 回复
    chat_history.append({"role": "assistant", "content": reply})
    if len(chat_history) > 10:
        del chat_history[:-10]

    return jsonify({"reply": reply}) 

@app.route('/records')
@login_required
def get_records():
    db = get_db()
    month = request.args.get("month")
    if month:
        cursor = db.execute(
            """
            SELECT *, strftime('%Y-%m', date) as month
            FROM records
            WHERE strftime('%Y-%m', date) = ? AND user_id = ?
            ORDER BY date DESC
        """,
            (month, g.user_id)
        )
    else:
        cursor = db.execute(
            """
            SELECT *, strftime('%Y-%m', date) as month
            FROM records
            WHERE user_id = ?
            ORDER BY date DESC
        """,
            (g.user_id,)
        )
    results = [dict(row) for row in cursor.fetchall()]
    return jsonify(results)

@app.route('/records/<int:record_id>', methods=['DELETE'])
@login_required
def delete_record(record_id):
    db = get_db()
    db.execute(
        "DELETE FROM records WHERE id = ? AND user_id = ?",
        (record_id, g.user_id)
    )
    db.commit()
    return jsonify({"success": True})

@app.route('/records/<int:record_id>', methods=['PUT'])
@login_required
def update_record(record_id):
    data = request.get_json()
    category = data.get('category', '').strip()
    amount = float(data.get('amount', 0))
    note = data.get('note', '').strip()
    date = data.get('date')
    month = date[:7] if date else ''
    year = date[:4] if date else ''
    db = get_db()
    db.execute(
        """
        UPDATE records SET category = ?, amount = ?, note = ?, date = ?, month = ?, year = ?
        WHERE id = ? AND user_id = ?
        """,
        (category, amount, note, date, month, year, record_id, g.user_id),
    )
    db.commit()
    return jsonify({"success": True})

@app.route('/income')
@login_required
def get_income():
    db = get_db()
    month = request.args.get("month")

    if month:
        cursor = db.execute(
            """
            SELECT id, category, amount, note, date, month, year
            FROM income
            WHERE month = ? AND user_id = ?
            ORDER BY date DESC
        """,
            (month, g.user_id)
        )
    else:
        cursor = db.execute(
            """
            SELECT id, category, amount, note, date, month, year
            FROM income
            WHERE user_id = ?
            ORDER BY date DESC
        """,
            (g.user_id,)
        )

    results = [dict(row) for row in cursor.fetchall()]

    # ✅ 防御式检查每条记录都有 date 字段
    for r in results:
        if "date" not in r or not r["date"]:
            r["date"] = r.get("month", "") + "-01"

    return jsonify(results)

@app.route('/income/<int:income_id>', methods=['DELETE'])
@login_required
def delete_income(income_id):
    db = get_db()
    db.execute(
        "DELETE FROM income WHERE id = ? AND user_id = ?",
        (income_id, g.user_id)
    )
    db.commit()
    return jsonify({"success": True})

@app.route('/income/<int:income_id>', methods=['PUT'])
@login_required
def update_income(income_id):
    data = request.get_json()
    category = data.get('category', '').strip()
    amount = float(data.get('amount', 0))
    note = data.get('note', '').strip()
    date = data.get('date')
    month = date[:7] if date else ''
    year = date[:4] if date else ''
    db = get_db()
    db.execute(
        """
        UPDATE income SET category = ?, amount = ?, note = ?, date = ?, month = ?, year = ?
        WHERE id = ? AND user_id = ?
        """,
        (category, amount, note, date, month, year, income_id, g.user_id),
    )
    db.commit()
    return jsonify({"success": True})

@app.route("/categories", methods=["GET"])
@login_required
def get_categories():
    db = get_db()
    category_type = request.args.get("type")

    type_map = {
        "income": "收入",
        "expense": "支出"
    }

    if category_type in type_map:
        cursor = db.execute(
            "SELECT * FROM categories WHERE type = ? AND user_id = ? ORDER BY name ASC",
            (type_map[category_type], g.user_id)
        )
    else:
        cursor = db.execute(
            "SELECT * FROM categories WHERE user_id = ? ORDER BY name ASC",
            (g.user_id,)
        )

    results = [dict(row) for row in cursor.fetchall()]
    if not isinstance(results, list):
        return jsonify([])  # 🛡 确保一定返回数组
    return jsonify(results)


month = datetime.now().strftime("%Y-%m")
@app.route('/budgets')
@login_required
def get_budgets():
    db = get_db()
    month = request.args.get('month')
    result = []

    if month:
        # ✅ 仅查指定月份支出类预算
        cursor = db.execute(
            """
            SELECT b.category, b.amount
            FROM budgets b
            JOIN categories c ON b.category = c.name AND c.user_id = b.user_id
            WHERE b.month = ? AND b.user_id = ? AND c.type = '支出'
        """,
            (month, g.user_id)
        )
        budgets = cursor.fetchall()

        cursor = db.execute(
            """
            SELECT category, SUM(amount) as total
            FROM records
            WHERE strftime('%Y-%m', date) = ? AND user_id = ?
            GROUP BY category
        """,
            (month, g.user_id)
        )
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
        cursor = db.execute(
            """
            SELECT b.category, b.amount, b.month
            FROM budgets b
            JOIN categories c ON b.category = c.name AND c.user_id = b.user_id
            WHERE b.user_id = ? AND c.type = '支出'
        """,
            (g.user_id,)
        )
        all_budgets = cursor.fetchall()

        cursor = db.execute(
            """
            SELECT category, strftime('%Y-%m', date) as month, SUM(amount) as total
            FROM records
            WHERE user_id = ?
            GROUP BY category, month
        """,
            (g.user_id,)
        )
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
@login_required
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
        db.execute(
            "INSERT INTO categories (user_id, name, type) VALUES (?, ?, ?)",
            (g.user_id, name, category_type)
        )
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route("/categories/<name>", methods=["DELETE"])
@login_required
def delete_category_manual(name):
    db = get_db()

    # ✅ 获取分类类型
    row = db.execute(
        "SELECT type FROM categories WHERE name = ? AND user_id = ?",
        (name, g.user_id)
    ).fetchone()
    if not row:
        return jsonify({"error": f"分类「{name}」不存在"}), 404

    category_type = row["type"]

    # ✅ 删除记录
    if category_type == "支出":
        db.execute("DELETE FROM records WHERE category = ? AND user_id = ?", (name, g.user_id))
        db.execute("DELETE FROM budgets WHERE category = ? AND user_id = ?", (name, g.user_id))
    elif category_type == "收入":
        db.execute("DELETE FROM income WHERE source = ? AND user_id = ?", (name, g.user_id))

    # ✅ 删除分类本身
    db.execute("DELETE FROM categories WHERE name = ? AND user_id = ?", (name, g.user_id))
    db.commit()

    return jsonify({"success": True})

@app.route("/budgets", methods=["POST"])
@login_required
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
    row = db.execute(
        "SELECT type FROM categories WHERE name = ? AND user_id = ?",
        (category, g.user_id)
    ).fetchone()
    if not row:
        return jsonify({"error": f"分类「{category}」不存在"}), 400
    if row["type"] != "支出":
        return jsonify({"error": f"分类「{category}」不是支出类型，无法设置预算"}), 400

    # ✅ 写入预算
    db.execute(
        """
        INSERT OR REPLACE INTO budgets (user_id, category, amount, cycle, month)
        VALUES (?, ?, ?, ?, ?)
    """,
        (g.user_id, category, amount, cycle, month)
    )
    db.commit()
    return jsonify({"success": True})



@app.route("/stats/monthly", methods=["GET"])
@login_required
def monthly_stats():
    db = get_db()
    year = request.args.get("year")
    if year:
        # 按年份过滤
        spend_cursor = db.execute(
            """
            SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total
            FROM records WHERE year = ? AND user_id = ?
            GROUP BY month
            """,
            (year, g.user_id),
        )
        income_cursor = db.execute(
            """
            SELECT month, SUM(amount) AS total
            FROM income WHERE year = ? AND user_id = ?
            GROUP BY month
            """,
            (year, g.user_id),
        )
    else:
        # 无年份限制，统计全部月份
        spend_cursor = db.execute(
            """
            SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total
            FROM records
            WHERE user_id = ?
            GROUP BY month
            """,
            (g.user_id,)
        )
        income_cursor = db.execute(
            """
            SELECT month, SUM(amount) AS total
            FROM income
            WHERE user_id = ?
            GROUP BY month
            """,
            (g.user_id,)
        )

    spend_data = {row['month']: float(row['total']) for row in spend_cursor.fetchall()}
    income_data = {row['month']: float(row['total']) for row in income_cursor.fetchall()}

    if year:
        months = [f"{year}-{i:02d}" for i in range(1, 13)]
    else:
        months = sorted(set(spend_data.keys()) | set(income_data.keys()), reverse=True)

    result = []
    for m in months:
        result.append({
            "month": m,
            "支出": spend_data.get(m, 0.0),
            "收入": income_data.get(m, 0.0)
        })

    return jsonify(result)

@app.route("/stats/by-category", methods=["GET"])
@login_required
def category_stats():
    db = get_db()
    month = request.args.get("month")
    year = request.args.get("year")

    if month:
        spend_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM records WHERE month = ? AND user_id = ? GROUP BY category",
            (month, g.user_id),
        )
        income_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM income WHERE month = ? AND user_id = ? GROUP BY category",
            (month, g.user_id),
        )
    elif year:
        spend_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM records WHERE year = ? AND user_id = ? GROUP BY category",
            (year, g.user_id),
        )
        income_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM income WHERE year = ? AND user_id = ? GROUP BY category",
            (year, g.user_id),
        )
    else:
        spend_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM records WHERE user_id = ? GROUP BY category",
            (g.user_id,)
        )
        income_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM income WHERE user_id = ? GROUP BY category",
            (g.user_id,)
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
@login_required
def summary_stats():
    db = get_db()
    month = request.args.get("month") or datetime.now().strftime("%Y-%m")

    # ✅ 查询该月总支出
    spend_cursor = db.execute(
        """
        SELECT SUM(amount) AS total
        FROM records
        WHERE month = ? AND user_id = ?
    """,
        (month, g.user_id)
    )
    spend_total = float(spend_cursor.fetchone()["total"] or 0.0)

    # ✅ 查询该月总收入
    income_cursor = db.execute(
        """
        SELECT SUM(amount) AS total
        FROM income
        WHERE month = ? AND user_id = ?
    """,
        (month, g.user_id)
    )
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
@login_required
def daily_stats():
    db = get_db()
    month = request.args.get("month")
    if not month:
        return jsonify({"error": "缺少参数 month"}), 400

    # 支出
    spend_cursor = db.execute(
        """
        SELECT date, SUM(amount) AS total
        FROM records
        WHERE strftime('%Y-%m', date) = ? AND user_id = ?
        GROUP BY date
    """,
        (month, g.user_id)
    )
    spend_map = {row['date']: float(row['total']) for row in spend_cursor.fetchall()}

    # 收入
    income_cursor = db.execute(
        """
        SELECT date, SUM(amount) AS total
        FROM income
        WHERE strftime('%Y-%m', date) = ? AND user_id = ?
        GROUP BY date
    """,
        (month, g.user_id)
    )
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

from waitress import serve
serve(app, host="0.0.0.0", port=5000)

