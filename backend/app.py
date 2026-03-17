from flask import Flask, request, jsonify, g, session, make_response
from db import init_db, get_db, add_chat_message, get_chat_history
from handlers import *
from dotenv import load_dotenv
import os, requests, secrets, json, time, uuid, random
from collections import defaultdict
from io import BytesIO
from flask_cors import CORS
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from llm_security_middleware import register_llm_security
try:
    from captcha.image import ImageCaptcha
    _CAPTCHA_AVAILABLE = True
except ImportError:
    _CAPTCHA_AVAILABLE = False
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

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

# ===== 验证码存储 =====
_captcha_store: dict = {}
_CAPTCHA_TTL = 300  # 5 分钟有效期
_CAPTCHA_CHARS = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'  # 去掉易混淆字符

def _clean_expired_captchas():
    now = time.time()
    expired = [k for k, v in list(_captcha_store.items()) if v['expires_at'] < now]
    for k in expired:
        del _captcha_store[k]

# ===== 登录频率限制 =====
_login_attempts: dict = defaultdict(list)
_LOGIN_MAX = 10
_LOGIN_LOCKOUT = 30 * 60  # 30 分钟

def _login_allowed(ip: str) -> bool:
    now = time.time()
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < _LOGIN_LOCKOUT]
    return len(_login_attempts[ip]) < _LOGIN_MAX

def _record_failure(ip: str):
    _login_attempts[ip].append(time.time())

def _clear_attempts(ip: str):
    _login_attempts.pop(ip, None)

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


@app.route("/api/captcha")
def get_captcha():
    if not _CAPTCHA_AVAILABLE:
        return jsonify({'error': 'captcha library not installed, run: pip install captcha'}), 501
    import base64
    _clean_expired_captchas()
    token = str(uuid.uuid4())
    chars = ''.join(random.choices(_CAPTCHA_CHARS, k=4))
    _captcha_store[token] = {'answer': chars, 'expires_at': time.time() + _CAPTCHA_TTL}
    image = ImageCaptcha(width=160, height=60)
    buf = BytesIO()
    image.generate_image(chars).save(buf, format='PNG')
    img_b64 = base64.b64encode(buf.getvalue()).decode()
    return jsonify({'token': token, 'image': 'data:image/png;base64,' + img_b64})


@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400

    # 验证码校验
    captcha_token = data.get("captcha_token", "").strip()
    captcha_input = data.get("captcha_input", "").strip().upper()
    entry = _captcha_store.get(captcha_token)
    if not entry or entry['expires_at'] < time.time():
        return jsonify({"error": "验证码已过期，请刷新"}), 400
    if captcha_input != entry['answer']:
        del _captcha_store[captcha_token]
        return jsonify({"error": "验证码错误"}), 400
    del _captcha_store[captcha_token]

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
    ip = request.headers.get("X-Real-IP") or request.remote_addr
    if not _login_allowed(ip):
        return jsonify({"error": "登录尝试次数过多，请 30 分钟后再试"}), 429

    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    db = get_db()
    row = db.execute(
        "SELECT id, password, is_admin FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if not row or not check_password_hash(row["password"], password):
        _record_failure(ip)
        return jsonify({"error": "用户名或密码错误"}), 400

    _clear_attempts(ip)
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


@app.route("/api/llm_config", methods=["DELETE"])
@login_required
def llm_config_reset():
    db = get_db()
    db.execute("DELETE FROM llm_config WHERE user_id = ?", (g.user_id,))
    db.commit()
    return jsonify({"success": True})

handlers = {
    "add_record": add_record,
    "add_income": add_income,
    "set_budget": set_budget,
    "update_budget": update_budget,
    "analyze_spend": analyze_spend,
    "add_category": add_category,
    "delete_category": delete_category,
    "budget_remain": budget_remain,
    "suggest_budgets": suggest_budgets,
    "query_income": query_income,
    "category_sum": category_sum,
    "search_records": search_records,
    "delete_record": delete_record,
    "delete_income": delete_income,
}

FINANCE_TOOLS = [
    {"type": "function", "function": {"name": "add_record", "description": "记录一笔支出",
        "parameters": {"type": "object", "required": ["分类", "金额"],
            "properties": {"分类": {"type": "string"}, "金额": {"type": "number"},
                           "备注": {"type": "string"}, "时间": {"type": "string", "description": "YYYY-MM-DD，默认今天"}}}}},
    {"type": "function", "function": {"name": "add_income", "description": "记录一笔收入",
        "parameters": {"type": "object", "required": ["分类", "金额"],
            "properties": {"分类": {"type": "string"}, "金额": {"type": "number"},
                           "备注": {"type": "string"}, "时间": {"type": "string", "description": "YYYY-MM-DD，默认今天"}}}}},
    {"type": "function", "function": {"name": "set_budget", "description": "设置某分类的月预算",
        "parameters": {"type": "object", "required": ["分类", "金额"],
            "properties": {"分类": {"type": "string"}, "金额": {"type": "number"},
                           "月份": {"type": "string", "description": "YYYY-MM，默认当月"}}}}},
    {"type": "function", "function": {"name": "update_budget", "description": "更新某分类的月预算",
        "parameters": {"type": "object", "required": ["分类", "金额"],
            "properties": {"分类": {"type": "string"}, "金额": {"type": "number"},
                           "月份": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "analyze_spend", "description": "整体消费分析，生成消费排行、收入排行和建议",
        "parameters": {"type": "object",
            "properties": {"月份": {"type": "string", "description": "YYYY-MM，默认当月"}}}}},
    {"type": "function", "function": {"name": "add_category", "description": "新增支出或收入分类",
        "parameters": {"type": "object", "required": ["分类"],
            "properties": {"分类": {"type": "string"},
                           "类型": {"type": "string", "enum": ["支出", "收入"]}}}}},
    {"type": "function", "function": {"name": "delete_category", "description": "删除分类及其所有记录",
        "parameters": {"type": "object", "required": ["分类"],
            "properties": {"分类": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "budget_remain", "description": "查询预算剩余",
        "parameters": {"type": "object",
            "properties": {"月份": {"type": "string", "description": "YYYY-MM，默认当月"},
                           "分类": {"type": "string", "description": "留空返回全部分类"}}}}},
    {"type": "function", "function": {"name": "suggest_budgets", "description": "根据历史消费智能推荐预算",
        "parameters": {"type": "object",
            "properties": {"总预算": {"type": "number"}}}}},
    {"type": "function", "function": {"name": "query_income", "description": "查询收入记录",
        "parameters": {"type": "object",
            "properties": {"分类": {"type": "string"}, "时间范围": {"type": "string"},
                           "全部": {"type": "string", "enum": ["是", "否"]}}}}},
    {"type": "function", "function": {"name": "category_sum", "description": "统计某分类或时间段的支出总额",
        "parameters": {"type": "object",
            "properties": {"分类": {"type": "string"},
                           "开始时间": {"type": "string", "description": "YYYY-MM-DD"},
                           "结束时间": {"type": "string", "description": "YYYY-MM-DD"}}}}},
    {"type": "function", "function": {"name": "search_records", "description": "查询支出明细列表（含记录ID），可按分类、时间、备注关键词筛选。删除前先调用此接口查看实际记录",
        "parameters": {"type": "object",
            "properties": {"分类": {"type": "string", "description": "支出分类，留空返回全部"},
                           "时间范围": {"type": "string", "description": "YYYY-MM-DD（某天）、YYYY-MM（某月）或YYYY（某年），留空返回最近记录"},
                           "关键词": {"type": "string", "description": "备注关键词，模糊匹配，如'麦当劳'、'滴滴'"},
                           "条数": {"type": "integer", "description": "返回条数，默认10，最多20"}}}}},
    {"type": "function", "function": {"name": "delete_record", "description": "按记录ID删除一条支出记录。请先用 search_records 查询获取ID再调用此接口",
        "parameters": {"type": "object", "required": ["记录ID"],
            "properties": {"记录ID": {"type": "integer", "description": "支出记录的唯一ID"}}}}},
    {"type": "function", "function": {"name": "delete_income", "description": "按记录ID删除一条收入记录。请先用 query_income（全部=是）查询获取ID再调用",
        "parameters": {"type": "object", "required": ["收入ID"],
            "properties": {"收入ID": {"type": "integer", "description": "收入记录的唯一ID"}}}}},
]

def call_llm_intent(message, llm=None):
    llm = llm or {}
    today_str = datetime.now().strftime("%Y-%m-%d")
    api_key = llm.get("apikey") or os.getenv("DEEPSEEK_API_KEY")
    url = llm.get("url") or "https://api.siliconflow.cn/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": llm.get("model") or "Pro/deepseek-ai/DeepSeek-V3",
        "temperature": 0.3,
        "tools": FINANCE_TOOLS,
        "tool_choice": "auto",
        "messages": [
            {"role": "system", "content": f"今天是 {today_str}。你是智能财务助手，根据用户输入调用合适的工具完成记账操作。用户有多个操作时可同时调用多个工具。闲聊时不调用工具。"},
            {"role": "user", "content": message}
        ]
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        data = res.json()
        if "error" in data:
            logger.error("LLM API 错误：%s", data["error"])
            return None
        return data
    except Exception as e:
        logger.error("LLM 调用失败: %s", e)
        return None

def call_llm_summary(user_msg, handler_result, llm=None):
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
        f"用户输入：{user_msg}\n"
        f"系统执行结果：{handler_result}\n"
        "请用自然语言总结这次操作及执行结果，并提出简短合理的建议（50字以内）,不要添加不必要的格式化符号。\n"
        "当系统执行结果涉及具体数值时，必须保留全部数值，严禁省略！\n"
        "回复尽量人性化且风趣。\n"
        "不要做()括起来的额外回复。\n"
        "如果用户此次操作为本月消费分析请求，给出消费行为详细分析及评分，此时不限制回答字数，必须分别分析当月消费和总体消费，严禁混淆分析！"
    )

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
        logger.error("DeepSeek API error: %s", result["error"])
        return "❌ 分析失败：" + result["error"].get("message", "未知错误")
    else:
        logger.error("DeepSeek API unexpected response: %s", result)
        return "❌ 分析失败：LLM 响应格式异常"

def call_llm_chat(history, llm=None):
    """当用户没有执行记账相关操作时，与其闲聊。"""
    llm = llm or {}
    api_key = llm.get("apikey") or os.getenv("DEEPSEEK_API_KEY")
    url = llm.get("url") or "https://api.siliconflow.cn/v1/chat/completions"
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
        "model": llm.get("model") or "Pro/deepseek-ai/DeepSeek-V3",
        "messages": messages,
    }

    try:
        res = requests.post(url, headers=headers, json=data, timeout=10)
        result = res.json()
        if "choices" in result:
            return result["choices"][0]["message"]["content"]
        elif "error" in result:
            logger.error("DeepSeek chat error: %s", result["error"])
            return "⚠️ 暂时无法回复"
        else:
            logger.error("DeepSeek chat unexpected response: %s", result)
            return "⚠️ 暂时无法回复"
    except Exception as e:
        logger.error("DeepSeek chat failed: %s", e)
        return "⚠️ 暂时无法回复"

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
        for k, v in dict(row).items():
            llm_cfg.setdefault(k, v)

    user_msg = data.get("message", "")
    latest_msg = user_msg.strip().split("\n")[-1] if isinstance(user_msg, str) else user_msg

    add_chat_message(g.user_id, "user", user_msg)
    chat_history = get_chat_history(g.user_id)

    response = call_llm_intent(latest_msg, llm_cfg)

    reply = None
    if response and "choices" in response:
        msg_obj = response["choices"][0].get("message", {})
        tool_calls = msg_obj.get("tool_calls")

        if tool_calls:
            results = []
            for tc in tool_calls:
                func_name = tc["function"]["name"]
                params = json.loads(tc["function"]["arguments"])
                if func_name in handlers:
                    if func_name == "suggest_budgets":
                        r = handlers[func_name](g.user_id, params, llm_cfg)
                    else:
                        r = handlers[func_name](g.user_id, params)
                    results.append(r)
            if results:
                llm_logger.info(f"Tools: {[tc['function']['name'] for tc in tool_calls]}")
                reply = call_llm_summary(latest_msg, "\n".join(results), llm_cfg)
        else:
            reply = msg_obj.get("content")

    if not reply:
        reply = call_llm_chat(chat_history, llm_cfg)

    add_chat_message(g.user_id, "assistant", reply)
    return jsonify({"reply": reply})

@app.route('/api/records')
@login_required
def get_records():
    db = get_db()

    try:
        page = max(1, int(request.args.get("page", 1)))
        limit = min(200, max(1, int(request.args.get("limit", 50))))
    except (ValueError, TypeError):
        page, limit = 1, 50
    offset = (page - 1) * limit

    category = request.args.get("category")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    month = request.args.get("month")
    if month and not start_date and not end_date:
        import calendar as _cal
        y, m = map(int, month.split('-'))
        start_date = f"{month}-01"
        end_date = f"{month}-{_cal.monthrange(y, m)[1]:02d}"

    conditions = ["r.user_id = ?"]
    params = [g.user_id]
    if category:
        conditions.append("r.category = ?")
        params.append(category)
    if start_date:
        conditions.append("r.date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("r.date <= ?")
        params.append(end_date)
    where = " AND ".join(conditions)

    total = db.execute(f"SELECT COUNT(*) FROM records r WHERE {where}", params).fetchone()[0]

    rows = db.execute(
        f"""
        WITH base AS (
            SELECT r.id, r.category, r.amount, r.note, r.date,
                   strftime('%Y-%m', r.date) as month,
                   SUM(r.amount) OVER (
                       PARTITION BY r.user_id, r.category, strftime('%Y-%m', r.date)
                       ORDER BY r.date, r.id
                       ROWS UNBOUNDED PRECEDING
                   ) as cumulative_spend
            FROM records r WHERE {where}
        )
        SELECT * FROM base ORDER BY date DESC, id DESC LIMIT ? OFFSET ?
        """,
        params + [limit, offset]
    ).fetchall()

    category_months = {(row['category'], row['month']) for row in rows}
    budget_map = {}
    for cat, mon in category_months:
        b = db.execute(
            "SELECT amount FROM budgets WHERE user_id = ? AND category = ? AND month = ?",
            (g.user_id, cat, mon)
        ).fetchone()
        if b:
            budget_map[f"{cat}_{mon}"] = float(b['amount'])

    results = []
    for row in rows:
        r = dict(row)
        key = f"{r['category']}_{r['month']}"
        budget = budget_map.get(key)
        r['left_budget'] = f"{budget - r['cumulative_spend']:.2f}" if budget is not None else '—'
        del r['cumulative_spend']
        results.append(r)

    return jsonify({"data": results, "total": total, "page": page, "limit": limit})

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
    db = get_db()
    db.execute(
        "UPDATE records SET category = ?, amount = ?, note = ?, date = ? WHERE id = ? AND user_id = ?",
        (category, amount, note, date, record_id, g.user_id),
    )
    db.commit()
    return jsonify({"success": True})

@app.route('/api/income')
@login_required
def get_income():
    db = get_db()

    try:
        page = max(1, int(request.args.get("page", 1)))
        limit = min(200, max(1, int(request.args.get("limit", 50))))
    except (ValueError, TypeError):
        page, limit = 1, 50
    offset = (page - 1) * limit

    category = request.args.get("category")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    month = request.args.get("month")
    if month and not start_date and not end_date:
        import calendar as _cal
        y, m = map(int, month.split('-'))
        start_date = f"{month}-01"
        end_date = f"{month}-{_cal.monthrange(y, m)[1]:02d}"

    conditions = ["user_id = ?"]
    params = [g.user_id]
    if category:
        conditions.append("category = ?")
        params.append(category)
    if start_date:
        conditions.append("date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date)
    where = " AND ".join(conditions)

    total = db.execute(f"SELECT COUNT(*) FROM income WHERE {where}", params).fetchone()[0]

    rows = db.execute(
        f"SELECT id, category, amount, note, date, strftime('%Y-%m', date) as month "
        f"FROM income WHERE {where} ORDER BY date DESC, id DESC LIMIT ? OFFSET ?",
        params + [limit, offset]
    ).fetchall()

    results = []
    for row in rows:
        r = dict(row)
        if not r.get("date"):
            r["date"] = (r.get("month") or "") + "-01"
        results.append(r)

    return jsonify({"data": results, "total": total, "page": page, "limit": limit})

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
    db = get_db()
    db.execute(
        "UPDATE income SET category = ?, amount = ?, note = ?, date = ? WHERE id = ? AND user_id = ?",
        (category, amount, note, date, income_id, g.user_id),
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
        db.execute("DELETE FROM income WHERE category = ? AND user_id = ?", (name, g.user_id))

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
            FROM records WHERE strftime('%Y', date) = ? AND user_id = ?
            GROUP BY month
            """,
            (year, g.user_id),
        )
        income_cursor = db.execute(
            """
            SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total
            FROM income WHERE strftime('%Y', date) = ? AND user_id = ?
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
            SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total
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
            "SELECT category AS name, SUM(amount) AS total FROM records WHERE strftime('%Y-%m', date) = ? AND user_id = ? GROUP BY category",
            (month, g.user_id),
        )
        income_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM income WHERE strftime('%Y-%m', date) = ? AND user_id = ? GROUP BY category",
            (month, g.user_id),
        )
    elif year:
        spend_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM records WHERE strftime('%Y', date) = ? AND user_id = ? GROUP BY category",
            (year, g.user_id),
        )
        income_cursor = db.execute(
            "SELECT category AS name, SUM(amount) AS total FROM income WHERE strftime('%Y', date) = ? AND user_id = ? GROUP BY category",
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
        WHERE strftime('%Y-%m', date) = ? AND user_id = ?
    """,
        (month, g.user_id)
    )
    spend_total = float(spend_cursor.fetchone()["total"] or 0.0)

    # ✅ 查询该月总收入
    income_cursor = db.execute(
        """
        SELECT SUM(amount) AS total
        FROM income
        WHERE strftime('%Y-%m', date) = ? AND user_id = ?
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