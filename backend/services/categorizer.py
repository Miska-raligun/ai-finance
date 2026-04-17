"""自动归类：基于备注查 category_cache，未命中走 LLM 并回写缓存。"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from functools import lru_cache

from db import get_db

logger = logging.getLogger(__name__)


def _normalize(note: str) -> str:
    """去除空白和标点，便于哈希命中。"""
    if not note:
        return ""
    s = re.sub(r"\s+", "", note)
    s = re.sub(r"[，。、,.\-_/!?！？]+", "", s)
    return s.lower()


def _hash_note(user_id: int, note: str) -> str:
    norm = _normalize(note)
    return hashlib.sha256(f"{user_id}|{norm}".encode("utf-8")).hexdigest()[:24]


def _user_categories(user_id: int) -> list[str]:
    rows = get_db().execute(
        "SELECT name FROM categories WHERE user_id = ? AND type = '支出'",
        (user_id,),
    ).fetchall()
    return [r["name"] for r in rows]


def lookup_cache(user_id: int, note: str) -> str | None:
    """命中缓存返回分类名，未命中返回 None。会更新 hits/updated_at。"""
    norm = _normalize(note)
    if not norm:
        return None
    h = _hash_note(user_id, note)
    db = get_db()
    row = db.execute(
        "SELECT category FROM category_cache WHERE user_id = ? AND note_hash = ?",
        (user_id, h),
    ).fetchone()
    if not row:
        return None
    db.execute(
        "UPDATE category_cache SET hits = hits + 1, updated_at = ? WHERE user_id = ? AND note_hash = ?",
        (datetime.utcnow().isoformat(timespec="seconds"), user_id, h),
    )
    db.commit()
    return row["category"]


def remember(user_id: int, note: str, category: str) -> None:
    if not note or not category:
        return
    h = _hash_note(user_id, note)
    db = get_db()
    db.execute(
        """
        INSERT INTO category_cache (user_id, note_hash, note_sample, category, hits, updated_at)
        VALUES (?, ?, ?, ?, 1, ?)
        ON CONFLICT(user_id, note_hash) DO UPDATE SET
            category = excluded.category,
            hits = category_cache.hits + 1,
            updated_at = excluded.updated_at
        """,
        (user_id, h, note[:64], category, datetime.utcnow().isoformat(timespec="seconds")),
    )
    db.commit()


def categorize(user_id: int, note: str, llm: dict | None = None) -> dict:
    """自动归类入口。返回 {"category": str, "source": "cache"|"llm"|"none", "confidence": float}。

    若用户尚无支出分类，直接返回 none。
    """
    if not note or not note.strip():
        return {"category": "", "source": "none", "confidence": 0.0}

    cached = lookup_cache(user_id, note)
    if cached:
        logger.info("category_cache HIT user=%s note=%s -> %s", user_id, note[:20], cached)
        return {"category": cached, "source": "cache", "confidence": 1.0}

    cats = _user_categories(user_id)
    if not cats:
        return {"category": "", "source": "none", "confidence": 0.0}

    from services.llm import call_llm_categorize
    picked = call_llm_categorize(note, cats, llm=llm)
    if picked and picked in cats:
        remember(user_id, note, picked)
        return {"category": picked, "source": "llm", "confidence": 0.8}
    return {"category": "", "source": "none", "confidence": 0.0}
