"""认证装饰器、验证码管理、登录频率限制"""
import time
import uuid
import random
from functools import wraps
from collections import defaultdict
from io import BytesIO
from flask import abort, request, jsonify, g, session

try:
    from captcha.image import ImageCaptcha
    CAPTCHA_AVAILABLE = True
except ImportError:
    CAPTCHA_AVAILABLE = False

# ===== 验证码存储 =====
_captcha_store: dict = {}
_CAPTCHA_TTL = 300  # 5 分钟有效期
_CAPTCHA_CHARS = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'  # 去掉易混淆字符


def clean_expired_captchas():
    now = time.time()
    expired = [k for k, v in list(_captcha_store.items()) if v['expires_at'] < now]
    for k in expired:
        del _captcha_store[k]


def generate_captcha() -> tuple[str, str, str]:
    """生成验证码，返回 (token, answer, base64_image)"""
    import base64
    clean_expired_captchas()
    token = str(uuid.uuid4())
    chars = ''.join(random.choices(_CAPTCHA_CHARS, k=4))
    _captcha_store[token] = {'answer': chars, 'expires_at': time.time() + _CAPTCHA_TTL}
    image = ImageCaptcha(width=160, height=60)
    buf = BytesIO()
    image.generate_image(chars).save(buf, format='PNG')
    img_b64 = base64.b64encode(buf.getvalue()).decode()
    return token, chars, img_b64


def validate_captcha(token: str, user_input: str) -> tuple[bool, str]:
    """校验验证码，返回 (是否通过, 错误信息)"""
    entry = _captcha_store.get(token)
    if not entry or entry['expires_at'] < time.time():
        return False, "验证码已过期，请刷新"
    if user_input.upper() != entry['answer']:
        del _captcha_store[token]
        return False, "验证码错误"
    del _captcha_store[token]
    return True, ""


# ===== 登录频率限制 =====
_login_attempts: dict = defaultdict(list)
_LOGIN_MAX = 10
_LOGIN_LOCKOUT = 30 * 60  # 30 分钟


def login_allowed(ip: str) -> bool:
    now = time.time()
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < _LOGIN_LOCKOUT]
    return len(_login_attempts[ip]) < _LOGIN_MAX


def record_failure(ip: str):
    _login_attempts[ip].append(time.time())


def clear_attempts(ip: str):
    _login_attempts.pop(ip, None)


# ===== 装饰器 =====

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            abort(401, description="未登录或会话已过期")
        g.user_id = user_id
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    """Require the current user to be an administrator."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            abort(403, description="需要管理员权限")
        g.user_id = session.get("user_id")
        return f(*args, **kwargs)
    return wrapper
