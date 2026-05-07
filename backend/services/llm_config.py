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


def public_view(cfg: dict[str, Any] | None) -> dict[str, Any]:
    """对外展示用：apikey 掩码处理，避免下发明文。"""
    if not cfg:
        return {}
    from crypto import mask_secret
    out = dict(cfg)
    out["apikey"] = mask_secret(cfg.get("apikey") or "")
    return out
