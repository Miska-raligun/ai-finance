from flask import Flask, request, jsonify
from db import init_db, get_db
from handlers import *
from dotenv import load_dotenv
import os, requests
from flask_cors import CORS


app = Flask(__name__)
CORS(app)
init_db()
load_dotenv()  # 加载 .env 文件

handlers = {
    "add_record": add_record,
    "set_budget": set_budget,
    "update_budget": update_budget,
    "analyze_spend": analyze_spend,
    "add_category": add_category,
    "delete_category": delete_category
}

# 意图别名映射
INTENT_ALIAS = {
    "记录支出": "add_record",
    "支出记录": "add_record",
    "add_record": "add_record"
}

def call_deepseek_intent(message):
    import os, requests

    api_key = os.getenv("DEEPSEEK_API_KEY")
    url = "https://api.siliconflow.cn/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    prompt = (
        "你是一个智能财务助理。请根据用户输入生成结构化的意图（intent）和参数（params）。\\n"
        "意图必须为：add_record, set_budget, update_budget, analyze_spend, add_category, delete_category。\\n"
        "请严格使用以下格式输出：\\n"
        "意图：add_record\\n"
        "参数：\\n"
        "分类：餐饮\\n"
        "金额：25\\n"
        "备注：麦当劳\\n"
        "时间：2025-06-08"
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
        "请用自然语言总结这次操作，并提出简短合理的建议（50字以内）,不要添加不必要的格式化符号\n"
        "回复尽量人性化且风趣\n"
        "不要做()括起来的额外回复\n"
        "如果用户此次操作为本月消费分析请求，请给出消费行为详细分析及评分。"
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

    # ✅ 自动填充当前日期
    from datetime import datetime
    params["时间"] = datetime.now().strftime("%Y-%m-%d")

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

        # 用 LLM 进行总结生成自然语言
        reply = call_deepseek_summary(user_msg, result)
    else:
        reply = "⚠️ 暂不支持该操作"

    return jsonify({"reply": reply})



@app.route("/records", methods=["GET"])
def get_records():
    db = get_db()
    cursor = db.execute("SELECT * FROM records ORDER BY date DESC")
    results = [dict(row) for row in cursor.fetchall()]
    return jsonify(results)

@app.route("/categories", methods=["GET"])
def get_categories():
    db = get_db()
    cursor = db.execute("SELECT * FROM categories ORDER BY name ASC")
    results = [dict(row) for row in cursor.fetchall()]
    return jsonify(results)


@app.route("/budgets", methods=["GET"])
def get_budgets():
    db = get_db()
    cursor = db.execute("SELECT * FROM budgets ORDER BY category ASC")
    results = [dict(row) for row in cursor.fetchall()]
    return jsonify(results)

@app.route("/categories", methods=["POST"])
def add_category_manual():
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "缺少分类名称"}), 400
    db = get_db()
    try:
        db.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/categories/<name>", methods=["DELETE"])
def delete_category_manual(name):
    db = get_db()
    db.execute("DELETE FROM categories WHERE name = ?", (name,))
    db.execute("DELETE FROM budgets WHERE category = ?", (name,))
    db.commit()
    return jsonify({"success": True})

@app.route("/budgets", methods=["POST"])
def set_budget_manual():
    data = request.get_json()
    category = data.get("category", "").strip()
    amount = float(data.get("amount", 0))
    cycle = data.get("cycle", "月")  # ✅ 默认值
    db = get_db()
    db.execute("INSERT OR REPLACE INTO budgets (category, amount, cycle) VALUES (?, ?, ?)", (category, amount, cycle))
    db.commit()
    return jsonify({"success": True})

@app.route("/stats/monthly", methods=["GET"])
def monthly_stats():
    db = get_db()
    cursor = db.execute("""
        SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total
        FROM records
        GROUP BY month ORDER BY month DESC
    """)
    return jsonify([dict(row) for row in cursor.fetchall()])


@app.route("/stats/by-category", methods=["GET"])
def category_stats():
    db = get_db()
    cursor = db.execute("""
        SELECT category, SUM(amount) AS total
        FROM records
        GROUP BY category ORDER BY total DESC
    """)
    return jsonify([dict(row) for row in cursor.fetchall()])
