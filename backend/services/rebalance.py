"""再平衡目标：LLM 现场推荐，不再依赖写死的类型→占比表。

流程：
1. 取用户的 asset_types + 当前 allocation.by_type + risk_level
2. 用 (user_id, allocation_sig, risk_level) 查 rebalance_cache；30 分钟内直接复用
3. 未命中或 force=True → 调 call_llm_rebalance_suggest → 写回缓存
4. 返回 {targets, rationale, drift, cached_at}
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from services.portfolio import compute_drift


CACHE_TTL_SECONDS = 30 * 60  # 30 分钟


def _sig(by_type: list[dict]) -> str:
    """对 by_type 生成稳定 hash，用作缓存键——金额取整到千元减少抖动。"""
    normalized = [
        {"type": row.get("type"), "value_k": int(float(row.get("value") or 0) / 1000)}
        for row in sorted(by_type, key=lambda r: r.get("type") or "")
    ]
    raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _load_cached(db, user_id: int, sig: str, risk_level: str | None) -> dict | None:
    row = db.execute(
        "SELECT targets_json, rationale, created_at FROM rebalance_cache "
        "WHERE user_id = ? AND allocation_sig = ? AND risk_level IS ?",
        (user_id, sig, risk_level),
    ).fetchone()
    if not row:
        return None
    age = int(time.time()) - int(row["created_at"])
    if age > CACHE_TTL_SECONDS:
        return None
    try:
        targets = json.loads(row["targets_json"])
    except json.JSONDecodeError:
        return None
    return {
        "targets": targets,
        "rationale": row["rationale"] or "",
        "cached_at": int(row["created_at"]),
    }


def _save_cache(db, user_id: int, sig: str, risk_level: str | None,
                targets: dict, rationale: str) -> int:
    now = int(time.time())
    db.execute(
        "INSERT OR REPLACE INTO rebalance_cache "
        "(user_id, allocation_sig, risk_level, targets_json, rationale, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, sig, risk_level, json.dumps(targets, ensure_ascii=False),
         rationale, now),
    )
    db.commit()
    return now


def suggest_rebalance(db, user_id: int, allocation: dict, risk_level: str | None,
                      types: list[dict], llm: dict | None = None,
                      force: bool = False) -> dict[str, Any]:
    """主入口：返回 {targets, rationale, drift, cached_at, source}。

    source ∈ {"cache", "llm", "empty"}；targets 空时仍返回空 drift，让前端友好展示。
    """
    by_type = allocation.get("by_type", [])
    if not by_type:
        return {"targets": {}, "rationale": "", "drift": [], "cached_at": None,
                "source": "empty"}

    sig = _sig(by_type)
    if not force:
        cached = _load_cached(db, user_id, sig, risk_level)
        if cached is not None:
            drift = _drift_from_targets(allocation, cached["targets"])
            return {**cached, "drift": drift, "source": "cache"}

    from services.llm import call_llm_rebalance_suggest
    result = call_llm_rebalance_suggest(
        risk_level, types, by_type, llm=llm,
    )
    if not result or not result.get("targets"):
        # LLM 失败：保留最近一次成功的缓存（即便已过 TTL），否则空配置
        row = db.execute(
            "SELECT targets_json, rationale, created_at FROM rebalance_cache "
            "WHERE user_id = ? AND risk_level IS ? "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id, risk_level),
        ).fetchone()
        if row:
            try:
                targets = json.loads(row["targets_json"])
            except json.JSONDecodeError:
                targets = {}
            if targets:
                return {
                    "targets": targets,
                    "rationale": (row["rationale"] or "") + "（⚠️ 本次 LLM 未响应，显示上次结果）",
                    "drift": _drift_from_targets(allocation, targets),
                    "cached_at": int(row["created_at"]),
                    "source": "cache",
                }
        return {"targets": {}, "rationale": "⚠️ LLM 暂未返回配比建议，请稍后重试",
                "drift": [], "cached_at": None, "source": "empty"}

    cached_at = _save_cache(db, user_id, sig, risk_level,
                             result["targets"], result.get("rationale", ""))
    drift = _drift_from_targets(allocation, result["targets"])
    return {
        "targets": result["targets"],
        "rationale": result.get("rationale", ""),
        "drift": drift,
        "cached_at": cached_at,
        "source": "llm",
    }


def _drift_from_targets(allocation: dict, targets: dict) -> list[dict]:
    # targets 传进来是 0~100，compute_drift 期望 0~1
    scaled = {k: (float(v) / 100.0) for k, v in (targets or {}).items()}
    return compute_drift(allocation, scaled)
