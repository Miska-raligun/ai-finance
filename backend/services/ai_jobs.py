"""通用的单次 AI 作业:提交立刻返回,结果轮询取。

为什么要有这层:财务体检、买之前问一下这类端点要跑一大段 LLM,同步 HTTP
会把连接挂上几分钟,同时踩三个坑——nginx 的 proxy_read_timeout、nginx 连续
超时后把上游熔断(表现就是莫名其妙的 503)、waitress 默认只有 4 个工作线程
被长请求占满。

和 travel_jobs 分开:那边是多步作业,要记每步的成败和进度;这里是单次调用,
只需要一个结果。共用一个线程池,统一兜住并发。
"""
from __future__ import annotations

import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable

from flask import current_app, g

from db import get_db

logger = logging.getLogger(__name__)

_EXECUTOR = ThreadPoolExecutor(
    max_workers=int(os.getenv("AI_JOB_WORKERS", "3")),
    thread_name_prefix="ai-job",
)

# kind -> 真正干活的函数。用注册表而不是闭包:作业是跨线程跑的,
# 而且将来若要在重启后续跑,也得能只凭 kind + input 把活找回来。
_RUNNERS: dict[str, Callable[[int, dict, dict | None], dict]] = {}
_lock = threading.Lock()


def register(kind: str, fn) -> None:
    with _lock:
        _RUNNERS[kind] = fn


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def submit(user_id: int, kind: str, payload: dict, llm: dict | None,
           *, dedup_key: str | None = None) -> int:
    """排一个作业。同一个 dedup_key 已经在跑就直接复用,不重复打 LLM。"""
    db = get_db()
    if dedup_key:
        row = db.execute(
            "SELECT id FROM ai_jobs WHERE user_id = ? AND dedup_key = ? "
            "AND status IN ('pending','running') ORDER BY id DESC LIMIT 1",
            (user_id, dedup_key),
        ).fetchone()
        if row:
            return row["id"]

    now = _now()
    cur = db.execute(
        "INSERT INTO ai_jobs (user_id, kind, dedup_key, status, input_json, "
        "created_at, updated_at) VALUES (?,?,?,'pending',?,?,?)",
        (user_id, kind, dedup_key, json.dumps(payload, ensure_ascii=False), now, now),
    )
    db.commit()
    job_id = cur.lastrowid
    # 把 app 传进去:worker 在自己的线程里开 app_context,这样跑的还是原来
    # 那套 get_db(),不用为异步再写一遍数据访问。
    _EXECUTOR.submit(_run, current_app._get_current_object(),
                     job_id, user_id, kind, payload, llm)
    return job_id


def get(user_id: int, job_id: int) -> dict | None:
    row = get_db().execute(
        "SELECT id, kind, status, result_json, error, created_at, updated_at "
        "FROM ai_jobs WHERE id = ? AND user_id = ?", (job_id, user_id),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["result"] = json.loads(d.pop("result_json") or "null")
    except (TypeError, ValueError):
        d["result"] = None
    return d


def cleanup_orphans() -> int:
    """启动时收尸:进程重启会让 pending/running 永远卡住,前端一直转圈。"""
    db = get_db()
    cur = db.execute(
        "UPDATE ai_jobs SET status = 'failed', error = '服务重启,任务中断', "
        "updated_at = ? WHERE status IN ('pending','running')", (_now(),),
    )
    db.commit()
    return cur.rowcount


def _set(job_id: int, **fields):
    fields["updated_at"] = _now()
    sets = ", ".join(f"{k} = ?" for k in fields)
    db = get_db()
    db.execute(f"UPDATE ai_jobs SET {sets} WHERE id = ?",
               list(fields.values()) + [job_id])
    db.commit()


def _run(app, job_id: int, user_id: int, kind: str,
         payload: dict, llm: dict | None) -> None:
    with app.app_context():
        # 配额统计和一部分 handler 直接读 g.user_id,补上,别让它们在
        # worker 里炸掉(routes/chat.py 的图片任务也是这么做的)
        g.user_id = user_id
        try:
            _set(job_id, status="running")
            fn = _RUNNERS.get(kind)
            if not fn:
                _set(job_id, status="failed", error=f"未注册的任务类型:{kind}")
                return
            result = fn(user_id, payload, llm)
            _set(job_id, status="done",
                 result_json=json.dumps(result, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            logger.exception("ai job %s (%s) 失败", job_id, kind)
            try:
                _set(job_id, status="failed", error=str(e)[:300] or "内部错误")
            except Exception:  # noqa: BLE001
                logger.exception("ai job %s 连失败都没记上", job_id)
