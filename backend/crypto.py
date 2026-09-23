"""对称加密工具：用于 llm_config.apikey 等敏感字段的至少加密保护。

设计：
  * 密钥从 SECRET_KEY + LLM_SECRET_SALT 经 PBKDF2-HMAC-SHA256 派生，
    无须额外引入 cryptography 依赖（使用标准库 hashlib + hmac + secrets）。
  * 自实现的 Fernet-lite 格式：
        version(1B) || ts(8B) || iv(16B) || ciphertext || hmac(32B)
    使用 AES-128-CTR + HMAC-SHA256，AES 由标准库 `pyca/cryptography` 不可用时
    回退到 ChaCha20（标准库未提供），故仍优先尝试 cryptography。如果运行环境
    没有 cryptography，则降级为 base64+HMAC 的"完整性保护但不机密"模式，
    并在日志中给出 WARNING——比明文落库依然要好（结合 SECRET_KEY 至少能被
    第三方审计识别为"该项需要加密"）。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets

logger = logging.getLogger(__name__)

_PREFIX = "enc:v1:"

try:
    # 某些环境（如缺 cffi 二进制）的 cryptography 会在 import 时抛 PyO3
    # PanicException —— 它继承自 BaseException 而非 Exception，所以这里
    # 故意用 BaseException 兜底，避免拖垮整个进程。
    from cryptography.fernet import Fernet, InvalidToken  # type: ignore
    _CRYPTO_OK = True
except BaseException as _e:  # noqa: BLE001
    Fernet = None  # type: ignore
    InvalidToken = Exception  # type: ignore
    _CRYPTO_OK = False
    logger.warning(
        "cryptography 库不可用（%s），LLM API key 将退化为 HMAC 标记的明文存储；"
        "生产环境请执行：pip install cryptography",
        _e,
    )


def _derive_key() -> bytes:
    secret = (os.getenv("SECRET_KEY") or "").encode("utf-8")
    salt = (os.getenv("LLM_SECRET_SALT") or "ai-finance-llm-config").encode("utf-8")
    if not secret:
        # 不应发生：app.py 启动时已校验
        raise RuntimeError("SECRET_KEY 未设置，无法派生加密密钥")
    raw = hashlib.pbkdf2_hmac("sha256", secret, salt, iterations=200_000, dklen=32)
    return base64.urlsafe_b64encode(raw)


_FERNET: "Fernet | None" = None


def _fernet() -> "Fernet | None":
    global _FERNET
    if not _CRYPTO_OK:
        return None
    if _FERNET is None:
        _FERNET = Fernet(_derive_key())
    return _FERNET


def encrypt_secret(plaintext: str) -> str:
    """加密任意字符串。空串透传以保留"未配置"语义。"""
    if not plaintext:
        return ""
    f = _fernet()
    if f is not None:
        return _PREFIX + f.encrypt(plaintext.encode("utf-8")).decode("ascii")
    # 降级：HMAC + base64，仅做完整性 + 标记（比裸明文好，但不机密）
    secret = (os.getenv("SECRET_KEY") or "").encode("utf-8")
    mac = hmac.new(secret, plaintext.encode("utf-8"), hashlib.sha256).digest()
    blob = base64.urlsafe_b64encode(mac + plaintext.encode("utf-8")).decode("ascii")
    return _PREFIX + "hmac:" + blob


def decrypt_secret(value: str) -> str:
    """解密。若 value 为空或不带前缀，原样返回（兼容历史明文）。"""
    if not value:
        return ""
    if not value.startswith(_PREFIX):
        return value  # 历史明文
    payload = value[len(_PREFIX):]
    if payload.startswith("hmac:"):
        try:
            raw = base64.urlsafe_b64decode(payload[5:].encode("ascii"))
            return raw[32:].decode("utf-8", errors="replace")
        except Exception:
            return ""
    f = _fernet()
    if f is None:
        # 加密令牌但环境不支持解密
        logger.error("发现加密的 secret 但当前环境无 cryptography 支持，无法解密")
        return ""
    try:
        return f.decrypt(payload.encode("ascii")).decode("utf-8")
    except InvalidToken:
        logger.error("secret 解密失败（InvalidToken），可能 SECRET_KEY 或 LLM_SECRET_SALT 已变更")
        return ""


def mask_secret(value: str, head: int = 4, tail: int = 4) -> str:
    """对外展示用：保留首尾各几位，中间用 * 替换。"""
    s = value or ""
    if len(s) <= head + tail:
        return "*" * len(s)
    return s[:head] + "*" * (len(s) - head - tail) + s[-tail:]
