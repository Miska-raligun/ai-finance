from flask import Flask, request, jsonify, g, session
from db import init_db, get_db, add_chat_message, get_chat_history
from handlers import *
from dotenv import load_dotenv
import os, requests, secrets
from flask_cors import CORS
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from llm_security_middleware import register_llm_security
import logging

init_db()
load_dotenv()  # 加载 .env 文件
app = Flask(__name__)
register_llm_security(app)
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(16))
CORS(app, supports_credentials=True)

# 初始化日志记录器
llm_logger = logging.getLogger("llm_return")
llm_logger.setLevel(logging.INFO)
if not llm_logger.handlers:
    handler = logging.FileHandler("llm_return.log", encoding="utf-8")
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    llm_logger.addHandler(handler)

# 在内存中维护最近10条对话记录
chat_history = []  # [{"role": "user"/"assistant", "content": "..."}]

# ===== 简易用户认证 =====

def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401
        g.user_id = user_id
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    """Require the current user to be an administrator."""
    from functools import wraps

    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return jsonify({"error": "Admin only"}), 403
        g.user_id = session.get("user_id")
        return f(*args, **kwargs)

    return wrapper


@app.route("/api/register", methods=["POST"])
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


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    db = get_db()
    row = db.execute(
        "SELECT id, password, is_admin FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if not row or not check_password_hash(row["password"], password):
        return jsonify({"error": "用户名或密码错误"}), 400

    session["user_id"] = row["id"]
    session["username"] = username
    session["is_admin"] = bool(row["is_admin"])
    return jsonify({"success": True, "is_admin": bool(row["is_admin"])})

@app.route("/api/logout", methods=["POST"])
@login_required
def logout():
    session.pop("user_id", None)
    session.pop("username", None)
    session.pop("is_admin", None)
    return jsonify({"success": True})


@app.route("/api/me", methods=["GET"])
@login_required
def get_me():
    """Return current user's basic info."""
    return jsonify(
        {
            "username": session.get("username"),
            "is_admin": bool(session.get("is_admin")),
        }
    )


@app.route("/api/llm_config", methods=["GET", "POST"])
@login_required
def llm_config_api():
    db = get_db()
    if request.method == "GET":
        row = db.execute(
            "SELECT url, apikey, model, persona FROM llm_config WHERE user_id = ?",
            (g.user_id,),
        ).fetchone()
        return jsonify(dict(row)) if row else jsonify({})

    data = request.get_json() or {}
    url = data.get("url", "").strip()
    apikey = data.get("apikey", "").strip()
    model = data.get("model", "").strip()
    persona = data.get("persona", "").strip()
    db.execute(
        """
        INSERT INTO llm_config (user_id, url, apikey, model, persona)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            url=excluded.url,
            apikey=excluded.apikey,
            model=excluded.model,
            persona=excluded.persona
        """,
        (g.user_id, url, apikey, model, persona),
    )
    db.commit()
    # Output the current config for debugging
    #print(
        #"Updated llm_config for user", g.user_id,
        #{"url": url, "apikey": apikey, "model": model, "persona": persona}
    #)
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
    "query_income": query_income,
    "category_sum": category_sum
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
        "你是智能财务助手。请严格按照以下要求处理用户输入：\n"
        "1. 你的唯一任务是：根据用户输入，准确提取结构化意图（intent）和参数（params）。\n"
        "2. 意图只能为以下之一，禁止自创、扩展或模糊表达：\n"
        "   - add_record（记录支出）\n"
        "   - add_income（记录收入）\n"
        "   - set_budget（设置预算）\n"
        "   - update_budget（更新预算）\n"
        "   - analyze_spend（整体消费分析，生成消费排行、收入排行和建议）\n"
        "   - add_category（新增分类）\n"
        "   - delete_category（删除分类）\n"
        "   - budget_remain（查询预算剩余）\n"
        "   - suggest_budgets（智能推荐预算）\n"
        "   - query_income（查询收入）\n"
        "   - category_sum（统计指定分类或时间范围内的消费总额）\n"
        "   - chat（普通闲聊）\n"
        "3. 具体参数要求：\n"
        "   - add_record、add_income：必须提取分类、金额、备注、时间（具体日期，如果没有涉及明确的日期说明，则默认为今天的消费）、月份（如 2025-06），分类不得为空！\n"
        "   - set_budget、update_budget：必须提取分类、金额、月份\n"
        "   - suggest_budgets：必须提取“总预算”字段\n"
        "   - analyze_spend：仅当用户明确表达“整体消费分析”、“消费习惯分析”、“消费排行”、“消费建议”时使用。禁止用于统计具体分类或金额。严禁与 category_sum 混淆。\n"
        "   - category_sum：仅用于统计“某分类”或“某时间段”的总消费金额。当用户使用“花了多少钱”、“消费总额”、“统计支出”、“总共花了多少”、“总消费”、“一共花了”类似表达时，必须使用 category_sum。即使用户未指定分类，仍使用 category_sum。\n"
        "   - query_income：可提取来源、时间范围、是否查询全部\n"
        "   - chat： 无需提取参数\n"
        "4. 当用户输入包含多个操作时，请为每个操作分别输出一组意图与参数，中间用空行隔开\n"
        "5. 严格遵循以下输出格式，禁止添加任何额外解释或符号：\n"
        "意图：add_record\n"
        "参数：\n"
        "分类：餐饮\n"
        "金额：25\n"
        "备注：麦当劳\n"
        "时间：2025-06-08\n"
        "月份：2025-06\n"
        "6. 请结合模糊时间表达推断出具体日期和月份，例如“今天、昨天、上周、5月1日”等\n"
        "7. 严禁输出多余内容\n"
        "8. 【示例】以下用户输入及正确输出：\n"
        "   - 用户输入：“帮我统计上周花了多少钱”\n"
        "     正确输出：\n"
        "     意图：category_sum\n"
        "     参数：\n"
        "     分类：\n"
        "     开始时间：2025-06-17\n"
        "     结束时间：2025-06-23\n"
        "   - 用户输入：“分析一下我上个月的消费情况”\n"
        "     正确输出：\n"
        "     意图：analyze_spend\n"
        "     参数：\n"
        "     月份：2025-05\n"
    )



    payload = {
        "model": llm.get("model") or "Pro/deepseek-ai/DeepSeek-V3",
        "temperature": 0.5,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": message}
        ]
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        data = res.json()
        #print("📥 DeepSeek 返回内容：", data)  # 打印原始返回，方便调试

        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        elif "error" in data:
            print("❌ DeepSeek API 错误：", data["error"])
            return "意图：unknown\n参数："
        else:
            print("❓ 未知格式响应：", data)
            return "意图：unknown\n参数："

    except Exception as e:
        print("DeepSeek 调用失败:", e)
        return "意图：unknown\n参数："

def call_deepseek_summary(user_msg, handler_result, llm=None):
    import os, requests

    llm = llm or {}

    api_key = llm.get("apikey") or os.getenv("DEEPSEEK_API_KEY")
    url = llm.get("url") or "https://api.siliconflow.cn/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    persona = llm.get("persona") or "一个有点傲娇的财务顾问"
    summary_prompt = (
        f"你是{persona}，你的名字叫Anon。请根据用户的操作结果进行总结和建议。\n"
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

    persona = llm.get("persona") or "一个有点傲娇的财务顾问"
    prompt = (
        f"你是{persona}，你的名字叫Anon。可以和用户闲聊，并在合适的时候提醒保持良好的记账习惯。\n"
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
    """Parse LLM structured output into a list of (intent, params) tuples."""
    blocks = [b for b in text.strip().split("\n\n") if b.strip()]
    results = []
    for block in blocks:
        lines = block.strip().split("\n")
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
        if intent:
            results.append((intent, params))
    return results

@app.route("/api/chat", methods=["POST"])
@login_required
def chat():
    data = request.get_json()
    llm_cfg = data.get("llm") or {}
    db = get_db()
    row = db.execute(
        "SELECT url, apikey, model, persona FROM llm_config WHERE user_id = ?",
        (g.user_id,),
    ).fetchone()
    if row:
        saved_cfg = dict(row)
        for k, v in saved_cfg.items():
            llm_cfg.setdefault(k, v)
    user_msg = data.get("message", "")
    latest_msg = user_msg
    if isinstance(user_msg, str):
        latest_msg = user_msg.strip().split("\n")[-1]

    # 记录对话历史到数据库
    add_chat_message(g.user_id, "user", user_msg)
    chat_history = get_chat_history(g.user_id)

    #print("最新消息: ",latest_msg)
    llm_output = call_deepseek_intent(latest_msg, llm_cfg)
    llm_logger.info(f"LLM：{llm_output}")

    intent_results = parse_response(llm_output)

    results = []
    for intent, params in intent_results:
        if intent in handlers:
            if intent == "suggest_budgets":
                r = handlers[intent](g.user_id, params, llm_cfg)
            else:
                r = handlers[intent](g.user_id, params)
            results.append(r)
            #print("📦 handler 执行结果：", r)

    if results:
        result = "\n".join(results)

        #if any(i[0] == "add_record" for i in intent_results):
            #from db import get_db
            #db = get_db()
            #cursor = db.execute("SELECT * FROM records ORDER BY date DESC")
            #print("📒 当前记录：")
            #for row in cursor.fetchall():
                #print(dict(row))

        #if any(i[0] == "add_income" for i in intent_results):
            #from db import get_db
            #db = get_db()
            #cursor = db.execute("SELECT * FROM income ORDER BY date DESC")
            #print("📒 当前记录：")
            #for row in cursor.fetchall():
                #print(dict(row))
        # 用 LLM 进行总结生成自然语言
        reply = call_deepseek_summary(latest_msg, result, llm_cfg)
    else:
        # 如果未识别出意图，直接和用户闲聊几句
        #print("llm输入:",chat_history)
        reply = call_deepseek_chat(chat_history, llm_cfg)

    # 记录 assistant 回复
    add_chat_message(g.user_id, "assistant", reply)

    return jsonify({"reply": reply}) 

@app.route('/api/records')
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
            ORDER BY date DESC, id DESC
        """,
            (month, g.user_id)
        )
    else:
        cursor = db.execute(
            """
            SELECT *, strftime('%Y-%m', date) as month
            FROM records
            WHERE user_id = ?
            ORDER BY date DESC, id DESC
        """,
            (g.user_id,)
        )
    results = [dict(row) for row in cursor.fetchall()]
    return jsonify(results)

@app.route('/api/records/<int:record_id>', methods=['DELETE'])
@login_required
def delete_record(record_id):
    db = get_db()
    db.execute(
        "DELETE FROM records WHERE id = ? AND user_id = ?",
        (record_id, g.user_id)
    )
    db.commit()
    return jsonify({"success": True})

@app.route('/api/records/<int:record_id>', methods=['PUT'])
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

@app.route('/api/income')
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
            ORDER BY date DESC, id DESC
        """,
            (month, g.user_id)
        )
    else:
        cursor = db.execute(
            """
            SELECT id, category, amount, note, date, month, year
            FROM income
            WHERE user_id = ?
            ORDER BY date DESC, id DESC
        """,
            (g.user_id,)
        )

    results = [dict(row) for row in cursor.fetchall()]

    # ✅ 防御式检查每条记录都有 date 字段
    for r in results:
        if "date" not in r or not r["date"]:
            r["date"] = r.get("month", "") + "-01"

    return jsonify(results)

@app.route('/api/income/<int:income_id>', methods=['DELETE'])
@login_required
def delete_income(income_id):
    db = get_db()
    db.execute(
        "DELETE FROM income WHERE id = ? AND user_id = ?",
        (income_id, g.user_id)
    )
    db.commit()
    return jsonify({"success": True})

@app.route('/api/income/<int:income_id>', methods=['PUT'])
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

@app.route("/api/categories", methods=["GET"])
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
@app.route('/api/budgets')
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

@app.route("/api/categories", methods=["POST"])
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



@app.route("/api/categories/<name>", methods=["DELETE"])
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

@app.route("/api/budgets", methods=["POST"])
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



@app.route("/api/stats/monthly", methods=["GET"])
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

@app.route("/api/stats/by-category", methods=["GET"])
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

@app.route("/api/stats/summary", methods=["GET"])
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

@app.route("/api/stats/daily")
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


# ===== 管理员接口 =====

@app.route("/api/users", methods=["GET"])
@admin_required
def list_users():
    """列出除当前管理员外的所有用户"""
    db = get_db()
    rows = db.execute(
        "SELECT id, username, is_admin FROM users WHERE id != ?",
        (session.get("user_id"),),
    ).fetchall()
    result = [
        {
            "id": r["id"],
            "username": r["username"],
            "is_admin": bool(r["is_admin"]),
        }
        for r in rows
    ]
    return jsonify(result)


@app.route("/api/users/<int:user_id>/password", methods=["PUT"])
@admin_required
def admin_change_password(user_id):
    data = request.get_json() or {}
    new_pwd = data.get("password", "").strip()
    if not new_pwd:
        return jsonify({"error": "缺少密码"}), 400
    db = get_db()
    db.execute(
        "UPDATE users SET password = ? WHERE id = ?",
        (generate_password_hash(new_pwd), user_id),
    )
    db.commit()
    return jsonify({"success": True})


@app.route("/api/users/batch_delete", methods=["POST"])
@admin_required
def admin_batch_delete():
    data = request.get_json() or {}
    ids = data.get("user_ids") or []
    if not isinstance(ids, list):
        return jsonify({"error": "user_ids 必须是列表"}), 400

    # 不允许删除自身
    ids = [i for i in ids if i != session.get("user_id")]
    if not ids:
        return jsonify({"success": True})

    placeholders = ",".join(["?"] * len(ids))
    db = get_db()
    with db:
        db.execute(f"DELETE FROM users WHERE id IN ({placeholders})", ids)
        db.execute(f"DELETE FROM records WHERE user_id IN ({placeholders})", ids)
        db.execute(f"DELETE FROM income WHERE user_id IN ({placeholders})", ids)
        db.execute(f"DELETE FROM categories WHERE user_id IN ({placeholders})", ids)
        db.execute(f"DELETE FROM budgets WHERE user_id IN ({placeholders})", ids)
        db.execute(f"DELETE FROM llm_config WHERE user_id IN ({placeholders})", ids)
        db.execute(f"DELETE FROM chat_history WHERE user_id IN ({placeholders})", ids)
    return jsonify({"success": True})