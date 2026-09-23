"""共享 blueprint + 工具函数。所有 investment 子模块都从这里 import。"""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, g

from db import get_db

investment_bp = Blueprint("investment", __name__)

TX_KINDS = {"buy", "sell", "dividend", "adjust"}
VALID_SHAPES = {"security_auto", "security_manual", "lump", "cash"}
AUTO_SHAPES = {"security_auto"}
VALID_QUOTE_SOURCES = {"stock", "fund"}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_asset_type(name: str) -> dict | None:
    row = get_db().execute(
        "SELECT id, name, shape, quote_source FROM asset_types "
        "WHERE user_id = ? AND name = ?",
        (g.user_id, name),
    ).fetchone()
    return dict(row) if row else None


def list_asset_types_db() -> list[dict]:
    rows = get_db().execute(
        "SELECT id, name, shape, quote_source, created_at FROM asset_types "
        "WHERE user_id = ? ORDER BY created_at ASC, id ASC",
        (g.user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def load_llm_cfg(data: dict) -> dict:
    """合并:请求体 > 用户存储的 llm_config > LLM 默认值。

    向后兼容的薄封装——具体合并逻辑已经统一到 services.llm_config.current_llm。
    """
    from services.llm_config import current_llm
    return current_llm(data)


def fetch_assets() -> list[dict]:
    rows = get_db().execute(
        "SELECT id, name, type, symbol, holdings, cost_basis, current_value, "
        "currency, notes, created_at, updated_at FROM assets WHERE user_id = ? "
        "ORDER BY current_value DESC",
        (g.user_id,),
    ).fetchall()
    return [dict(r) for r in rows]
