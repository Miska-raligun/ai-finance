import logging
import os
import requests
from flask import request, abort
from dotenv import load_dotenv
from collections import defaultdict, deque
import time

# 记录被拦截次数
ip_block_counts = defaultdict(int)

# 记录被封禁的 IP 和解封时间戳
ip_blacklist = {}
BLOCK_THRESHOLD = 3       # 连续被 block 次数
BLOCK_DURATION = 3600     # 封禁时长（秒）

# 404 扫描检测：滑动窗口
ip_404_times = defaultdict(deque)
NOT_FOUND_THRESHOLD = 8   # 窗口内触发封禁的 404 次数
NOT_FOUND_WINDOW = 60     # 滑动窗口大小（秒）

# 请求频率限制：滑动窗口（仅非白名单路径）
ip_req_times = defaultdict(deque)
RATE_LIMIT_THRESHOLD = 60  # 窗口内最大请求数
RATE_LIMIT_WINDOW = 60     # 滑动窗口大小（秒）

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

不需要解释，严禁返回额外的解释信息！
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
    "/api/me", "/api/login", "/api/logout", "/api/chat", "/api/register",
    "/api/captcha",
    "/api/categories", "/api/income", "/api/records",
    "/api/stats", "/api/budgets", "/api/llm_config", "/api/heartbeat",
    "/api/users"
)

def is_whitelisted(path):
    return any(path.startswith(prefix) for prefix in WHITELIST_PREFIXES)

def _ban_ip(ip, reason):
    """封禁 IP 并记录日志。"""
    ip_blacklist[ip] = time.time() + BLOCK_DURATION
    sec_logger.warning(f"[BANNED] {ip} 封禁 {BLOCK_DURATION}s，原因：{reason}")

def _check_blacklist(ip):
    """检查是否在封禁名单，已过期则移除。返回 True 表示仍在封禁中。"""
    if ip in ip_blacklist:
        if time.time() < ip_blacklist[ip]:
            return True
        del ip_blacklist[ip]
    return False

def _sliding_window_count(dq, window):
    """清理滑动窗口过期记录，追加当前时间，返回窗口内计数。"""
    now = time.time()
    while dq and dq[0] < now - window:
        dq.popleft()
    dq.append(now)
    return len(dq)

def register_llm_security(app):
    @app.before_request
    def enforce_llm_policy():
        ip = request.headers.get("X-Real-IP") or request.remote_addr

        # ✅ 封禁名单检查
        if _check_blacklist(ip):
            sec_logger.warning(f"[BLACKLIST BLOCKED] {ip} 封禁中，拒绝访问")
            return abort(403)

        # ✅ 白名单直接放行，不计入频率统计
        if is_whitelisted(request.path):
            sec_logger.info(f"[WHITELIST] {ip} → {request.path}")
            return

        # ✅ 非白名单请求频率检测
        req_count = _sliding_window_count(ip_req_times[ip], RATE_LIMIT_WINDOW)
        if req_count > RATE_LIMIT_THRESHOLD:
            _ban_ip(ip, f"请求过于频繁 {req_count}次/{RATE_LIMIT_WINDOW}s")
            return abort(429)

        req_info = {
            "ip": ip,
            "method": request.method,
            "path": request.path,
            "user_agent": request.headers.get("User-Agent", ""),
            "content_length": request.content_length or 0
        }

        decision = query_llm_for_decision(req_info)
        sec_logger.info(f"[DECISION] {ip} → {req_info['path']} → {decision}")

        if decision == "block":
            ip_block_counts[ip] += 1
            sec_logger.warning(f"[BLOCK] {ip} 第 {ip_block_counts[ip]} 次")

            if ip_block_counts[ip] >= BLOCK_THRESHOLD:
                _ban_ip(ip, f"LLM 连续 block {ip_block_counts[ip]} 次")
            return abort(403)

        elif decision == "warn":
            sec_logger.warning(f"[WARN] {ip} → {req_info['path']}")
        elif decision == "log":
            sec_logger.info(f"[LOG] {ip} → {req_info['path']}")


    @app.errorhandler(404)
    def not_found(e):
        ip = request.headers.get("X-Real-IP") or request.remote_addr
        sec_logger.warning(f"[404] {ip} → {request.path}")

        # ✅ 404 扫描检测：短时间内大量 404 → 封禁
        count_404 = _sliding_window_count(ip_404_times[ip], NOT_FOUND_WINDOW)
        if count_404 >= NOT_FOUND_THRESHOLD:
            ip_404_times[ip].clear()
            _ban_ip(ip, f"{NOT_FOUND_WINDOW}s 内触发 {count_404} 次 404")

        return "404 Not Found", 404
