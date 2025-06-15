import logging
import os
import requests
from flask import request, abort
from dotenv import load_dotenv

load_dotenv()

LLM_MODEL = "Pro/deepseek-ai/DeepSeek-V3"  # 如需更换，请根据实际支持的模型名称
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY_WAF")
DEEPSEEK_API_URL = "https://api.siliconflow.cn/v1/chat/completions"

# 初始化日志记录器
sec_logger = logging.getLogger("llm_security")
sec_logger.setLevel(logging.INFO)
if not sec_logger.handlers:
    handler = logging.FileHandler("llm_security.log", encoding="utf-8")
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    sec_logger.addHandler(handler)

def query_llm_for_decision(request_info):
    prompt = f"""
你是一个 Web 安全代理，请根据以下请求信息判断该请求的安全策略。

返回值必须是以下 3 个之一（全小写）：
- log：记录但不警告；
- warn：打警告日志；
- block：拦截返回 403。

请求信息如下：
IP: {request_info['ip']}
Method: {request_info['method']}
Path: {request_info['path']}
User-Agent: {request_info['user_agent']}
Content-Length: {request_info['content_length']}
""".strip()

    try:
        res = requests.post(
            DEEPSEEK_API_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1
            },
            timeout=10
        )
        response = res.json()
        if isinstance(response, dict) and "choices" in response:
            return response["choices"][0]["message"]["content"].strip().lower()
        else:
            sec_logger.error("[LLM ERROR] Unexpected response format.")
            return "log"
    except Exception as e:
        sec_logger.error(f"[LLM ERROR] {e}")
        return "log"

# ✅ 路径前缀白名单（匹配 /api/ 和前端路径）
WHITELIST_PREFIXES = (
    "/login", "/chat", "/ledger", "/admin",
    "/api/me", "/api/login", "/api/logout",
    "/api/categories", "/api/income", "/api/records",
    "/api/stats", "/api/budgets", "/api/llm_config", "/api/heartbeat"
)

def is_whitelisted(path):
    return any(path.startswith(prefix) for prefix in WHITELIST_PREFIXES)

def register_llm_security(app):
    @app.before_request
    def enforce_llm_policy():
        ip = request.headers.get("X-Real-IP") or request.remote_addr
        req_info = {
            "ip": ip,
            "method": request.method,
            "path": request.path,
            "user_agent": request.headers.get("User-Agent", ""),
            "content_length": request.content_length or 0
        }

        # ✅ 如果在白名单中，直接放行
        if is_whitelisted(req_info["path"]):
            sec_logger.info(f"[WHITELIST] {ip} → {req_info['path']}")
            return

        decision = query_llm_for_decision(req_info)
        sec_logger.info(f"[DECISION] {ip} → {req_info['path']} → {decision}")

        if decision == "block":
            sec_logger.warning(f"[BLOCK] {ip} → {req_info['path']}")
            abort(403)
        elif decision == "warn":
            sec_logger.warning(f"[WARN] {ip} → {req_info['path']}")
        elif decision == "log":
            sec_logger.info(f"[LOG] {ip} → {req_info['path']}")
        # allow 不记录

    @app.errorhandler(404)
    def not_found(e):
        ip = request.headers.get("X-Real-IP") or request.remote_addr
        sec_logger.warning(f"[404] {ip} → {request.path}")
        return "404 Not Found", 404



