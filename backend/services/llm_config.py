"""llm_config 表的统一读写入口：解密 / 加密 / persona 长度限制。

历史明文记录由 crypto.decrypt_secret 透传，因此可以平滑迁移；下次保存时会自动加密。
"""
from __future__ import annotations

import re
from typing import Any

from db import get_db
from crypto import encrypt_secret, decrypt_secret

# Persona 是会被拼进 LLM system prompt 的用户可控字段，需要严格的长度与字符限制
# 以降低 prompt injection 影响（仍无法完全消除，但足以阻断"忽略以上指令"等常见尝试）。
_PERSONA_MAX_LEN = 200
_PERSONA_BAD_PATTERN = re.compile(
    r"(忽略.{0,8}(以上|之前|前面)|ignore\s+(all|previous|the).{0,30}instructions?|"
    r"you\s+are\s+now|系统提示|system\s+prompt|reveal\s+.*prompt)",
    re.IGNORECASE,
)


def _sanitize_persona(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    # 去掉控制字符与零宽字符
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f​-‏‪-‮]", "", s)
    if _PERSONA_BAD_PATTERN.search(s):
        # 不直接抛错以免阻断用户保存；改为截断 + 标注
        s = "[已过滤的人设]"
    if len(s) > _PERSONA_MAX_LEN:
        s = s[:_PERSONA_MAX_LEN]
    return s


VALID_PROVIDERS = {"openai", "anthropic", "gemini"}


def _normalize_provider(value: str | None) -> str:
    v = (value or "openai").strip().lower()
    return v if v in VALID_PROVIDERS else "openai"


def get_llm_config(user_id: int) -> dict | None:
    """读取并自动解密 apikey。返回 dict 或 None。"""
    row = get_db().execute(
        "SELECT url, apikey, model, persona, provider FROM llm_config WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if not row:
        return None
    cfg = dict(row)
    cfg["apikey"] = decrypt_secret(cfg.get("apikey") or "")
    cfg["provider"] = _normalize_provider(cfg.get("provider"))
    return cfg


def save_llm_config(user_id: int, *, url: str, apikey: str, model: str,
                    persona: str, provider: str = "openai") -> None:
    """保存配置：apikey 加密、persona 过滤后入库。"""
    enc_key = encrypt_secret((apikey or "").strip())
    safe_persona = _sanitize_persona(persona or "")
    safe_provider = _normalize_provider(provider)
    get_db().execute(
        """
        INSERT INTO llm_config (user_id, url, apikey, model, persona, provider)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            url=excluded.url,
            apikey=excluded.apikey,
            model=excluded.model,
            persona=excluded.persona,
            provider=excluded.provider
        """,
        (user_id, (url or "").strip(), enc_key, (model or "").strip(),
         safe_persona, safe_provider),
    )
    get_db().commit()


def current_llm(request_data: dict | None = None) -> dict:
    """取当前请求用户的有效 LLM 配置:请求体里临时传的 llm 字段优先,缺省字段
    用 llm_config 表兜底。

    系统默认判定:用户既没在请求里、也没在 llm_config 表里提供**自己的 apikey**,
    即视为「走系统默认」——此时 url / model / provider 一律取 constants.py
    (+ _call_llm 内部的 DEEPSEEK_API_KEY env),**忽略 llm_config 里可能残留的旧
    url / model**。否则改了 constants.py 也不生效(残留的旧 model 会一直盖过它)。
    persona 属个性化,不受影响,保留。

    各路由原本各写一份相同的 merge(checkup / reports / decide / chat / investment),
    集中到这里之后所有端点口径一致,改一处即可。

    必须在 Flask 请求上下文里调用(依赖 flask.g.user_id)。
    """
    from flask import g
    from constants import DEFAULT_LLM_URL, DEFAULT_LLM_MODEL

    cfg = dict((request_data or {}).get("llm") or {})
    stored = get_llm_config(g.user_id) or {}
    for k, v in stored.items():
        cfg.setdefault(k, v)

    if not (cfg.get("apikey") or "").strip():
        # 无用户自有 key → 系统默认:url/model 强制走 constants.py,provider 回落
        # openai 兼容(_call_llm 对 provider 缺省即 openai)。
        cfg["url"] = DEFAULT_LLM_URL
        cfg["model"] = DEFAULT_LLM_MODEL
        cfg.pop("provider", None)
    return cfg


def public_view(cfg: dict[str, Any] | None) -> dict[str, Any]:
    """对外展示用：apikey 掩码处理，避免下发明文。"""
    if not cfg:
        return {}
    from crypto import mask_secret
    out = dict(cfg)
    out["apikey"] = mask_secret(cfg.get("apikey") or "")
    return out
