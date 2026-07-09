"""轻量 TTL 缓存：用于统计/图表查询，按 user_id 维度失效。

设计原则：
- 进程内缓存（单进程 Flask + waitress 已足够）。多进程部署时需切换 Redis。
- 写操作（add/update/delete records, income, budgets）调用 invalidate_user 即可。
- 加锁防止并发读写竞态。
"""
from __future__ import annotations

import threading
from typing import Any, Callable

try:
    from cachetools import TTLCache
except ImportError:  # 兜底：cachetools 未安装时退化为无缓存
    TTLCache = None  # type: ignore

_DEFAULT_TTL = 60
_DEFAULT_MAXSIZE = 1024

_lock = threading.RLock()
_cache: dict[str, Any] | None = None


def _get_cache():
    global _cache
    if _cache is None:
        if TTLCache is None:
            _cache = {}
        else:
            _cache = TTLCache(maxsize=_DEFAULT_MAXSIZE, ttl=_DEFAULT_TTL)
    return _cache


def make_key(user_id: int, namespace: str, **params) -> str:
    parts = [f"u={user_id}", f"ns={namespace}"]
    for k in sorted(params.keys()):
        v = params[k]
        if v is None or v == "":
            continue
        parts.append(f"{k}={v}")
    return "|".join(parts)


def get(key: str):
    with _lock:
        try:
            return _get_cache().get(key)
        except KeyError:
            return None


def set(key: str, value: Any) -> None:
    with _lock:
        try:
            _get_cache()[key] = value
        except Exception:
            pass


def get_or_compute(key: str, compute: Callable[[], Any]) -> Any:
    cached = get(key)
    if cached is not None:
        return cached
    value = compute()
    if value is not None:
        set(key, value)
    return value


def invalidate_user(user_id: int) -> None:
    """清空指定用户的所有缓存条目(进程内 TTL 缓存 + DB 落盘的 recap 缓存)。"""
    prefix = f"u={user_id}|"
    with _lock:
        cache = _get_cache()
        if isinstance(cache, dict):
            keys = [k for k in cache if k.startswith(prefix)]
        else:
            keys = [k for k in list(cache.keys()) if k.startswith(prefix)]
        for k in keys:
            try:
                del cache[k]
            except KeyError:
                pass
    _invalidate_recap_cache(user_id)


def _invalidate_recap_cache(user_id: int) -> None:
    """连带清掉 DB 里的本月回顾缓存(recap_cache 表)。

    放在这里而不是各写路径:所有 records/income 写操作按约定都会调
    invalidate_user,挂在这一个入口就覆盖 REST / MCP / chat / cron 全部路径,
    以后新增写路径也自动生效。资产类写操作会多删一次 recap——无害,下次
    访问重算即可。表不存在(老库未迁移)或 DB 异常时静默跳过,不影响主流程。
    """
    try:
        from db import get_db
        from flask import has_app_context
        db = get_db()
        db.execute("DELETE FROM recap_cache WHERE user_id = ?", (user_id,))
        db.commit()
        # Flask 上下文外 get_db 返回独立连接,调用方负责关闭
        if not has_app_context():
            db.close()
    except Exception:  # noqa: BLE001 — 缓存失效永远不能拖垮业务写入
        pass


def clear_all() -> None:
    with _lock:
        cache = _get_cache()
        if hasattr(cache, "clear"):
            cache.clear()
