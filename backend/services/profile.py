"""用户长期画像：从 chat_history 中提炼结构化 facts，注入未来对话。"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from db import get_db, get_chat_history

logger = logging.getLogger(__name__)


def get_profile(user_id: int) -> dict | None:
    row = get_db().execute(
        "SELECT facts_json, income_band, family_size, mortgage, updated_at FROM user_profile "
        "WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if not row:
        return None
    out = dict(row)
    if out.get("facts_json"):
        try:
            out["facts"] = json.loads(out["facts_json"])
        except json.JSONDecodeError:
            out["facts"] = None
    out.pop("facts_json", None)
    return out


def save_profile(user_id: int, facts: dict) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    db = get_db()
    db.execute(
        """
        INSERT INTO user_profile (user_id, facts_json, income_band, family_size, mortgage, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            facts_json = excluded.facts_json,
            income_band = excluded.income_band,
            family_size = excluded.family_size,
            mortgage = excluded.mortgage,
            updated_at = excluded.updated_at
        """,
        (
            user_id,
            json.dumps(facts.get("facts") or facts, ensure_ascii=False),
            facts.get("income_band"),
            facts.get("family_size"),
            facts.get("mortgage"),
            now,
        ),
    )
    db.commit()


def refresh_profile(user_id: int, llm: dict | None = None) -> dict:
    """读最近聊天历史 + 旧 facts，调 LLM 提取，落库返回新 facts。"""
    history = get_chat_history(user_id)
    if not history:
        return {"facts": None, "updated": False}

    old = get_profile(user_id) or {}
    from services.llm import call_llm_profile_extract
    new_facts = call_llm_profile_extract(history, old.get("facts"), llm=llm)
    if not new_facts:
        return {"facts": old.get("facts"), "updated": False}
    save_profile(user_id, new_facts)
    return {"facts": new_facts.get("facts") or new_facts, "updated": True}


def context_message(user_id: int) -> str | None:
    """返回供 chat 注入的简短 system 段落，无画像返回 None。"""
    p = get_profile(user_id)
    if not p:
        return None
    facts = p.get("facts")
    if not facts:
        return None
    try:
        facts_str = json.dumps(facts, ensure_ascii=False)
    except (TypeError, ValueError):
        return None
    return (
        "以下是该用户在过往对话中沉淀的长期事实，回答时可参考但不要直接背诵：\n"
        + facts_str
    )
