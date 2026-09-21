"""后台 AI 作业:提交立刻返回 job_id,进度和结果轮询取。

为什么要有这层:跑一大段 LLM 的端点如果同步返回,HTTP 连接要挂上几分钟,
同时踩三个坑——nginx 的 proxy_read_timeout、nginx 连续超时后把上游熔断
(表现就是莫名其妙的 503)、以及 waitress 默认只有 4 个工作线程被长请求占满。

单步和多步是同一件事:单步就是步骤数为 1。所以只有这一张表、一个线程池、
一个状态端点。多步作业(比如整趟行程生成)把每步的成败记在 steps_json 里,
失败只重跑那一步,不用整件重来。

runner 用注册表而不是闭包:作业跨线程跑,而且将来若要在重启后续跑,
也得能只凭 kind + input 把活找回来。
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

# 合并前两个池各管各的(3 + 2),加起来能同时打 5 个 LLM,谁也不知道谁。
# 一个池才说得清并发上限。
_EXECUTOR = ThreadPoolExecutor(
    max_workers=int(os.getenv("AI_JOB_WORKERS", "4")),
    thread_name_prefix="ai-job",
)

_RUNNERS: dict[str, Callable[["JobCtx"], dict | None]] = {}
_lock = threading.Lock()
# 已取消的 job id。库里也会写 status='cancelled',这个集合只是让正在跑的
# worker 少查几次库、早一步停手。
_cancelled: set[int] = set()

_TERMINAL = ("done", "failed", "cancelled")


def register(kind: str, fn: Callable[["JobCtx"], dict | None]) -> None:
    with _lock:
        _RUNNERS[kind] = fn


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------- 作业上下文:runner 拿到的唯一入参 ----------

class JobCtx:
    """一个正在跑的作业。

    runner 在 worker 线程的 app_context 里被调用,所以照常用 get_db()
    就行,不必为异步再写一套数据访问。
    """

    def __init__(self, job_id: int, user_id: int, kind: str,
                 payload: dict, llm: dict | None, trip_id: int | None):
        self.job_id = job_id
        self.user_id = user_id
        self.kind = kind
        self.payload = payload
        self.llm = llm
        self.trip_id = trip_id

    # -- 多步作业用 --

    @property
    def steps(self) -> list[dict]:
        row = get_db().execute(
            "SELECT steps_json FROM ai_jobs WHERE id = ?", (self.job_id,)).fetchone()
        try:
            return json.loads(row["steps_json"] or "[]") if row else []
        except (TypeError, ValueError):
            return []

    def set_steps(self, steps: list[dict]) -> None:
        done = sum(1 for s in steps if s["status"] in ("done", "failed", "skipped"))
        _set(self.job_id, steps_json=json.dumps(steps, ensure_ascii=False),
             done=done, total=len(steps))

    def set_trip(self, trip_id: int) -> None:
        self.trip_id = trip_id
        _set(self.job_id, trip_id=trip_id)

    @property
    def cancelled(self) -> bool:
        with _lock:
            if self.job_id in _cancelled:
                return True
        row = get_db().execute(
            "SELECT status FROM ai_jobs WHERE id = ?", (self.job_id,)).fetchone()
        return bool(row and row["status"] == "cancelled")


# ---------- 提交 / 查询 ----------

def submit(user_id: int, kind: str, payload: dict, llm: dict | None,
           *, dedup_key: str | None = None, trip_id: int | None = None) -> int:
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
        "INSERT INTO ai_jobs (user_id, kind, dedup_key, trip_id, status, input_json, "
        "steps_json, done, total, created_at, updated_at) "
        "VALUES (?,?,?,?,'pending',?,'[]',0,0,?,?)",
        (user_id, kind, dedup_key, trip_id,
         json.dumps(payload, ensure_ascii=False), now, now),
    )
    db.commit()
    job_id = cur.lastrowid
    _start(job_id, user_id, kind, payload, llm, trip_id)
    return job_id


def _start(job_id, user_id, kind, payload, llm, trip_id) -> None:
    # 把 app 传进去:worker 在自己的线程里开 app_context,这样跑的还是原来
    # 那套 get_db(),不用为异步再写一遍数据访问。
    _EXECUTOR.submit(_run, current_app._get_current_object(),
                     job_id, user_id, kind, payload, llm, trip_id)


def get(user_id: int, job_id: int) -> dict | None:
    row = get_db().execute(
        "SELECT id, kind, trip_id, status, result_json, steps_json, done, total, "
        "error, created_at, updated_at FROM ai_jobs WHERE id = ? AND user_id = ?",
        (job_id, user_id),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    # input_json 不回传:行程单原文能有两万字,轮询每秒来一次
    for src, dst, empty in (("result_json", "result", "null"),
                            ("steps_json", "steps", "[]")):
        try:
            d[dst] = json.loads(d.pop(src) or empty)
        except (TypeError, ValueError):
            d[dst] = None if dst == "result" else []
    return d


def list_jobs(user_id: int, *, kinds: tuple[str, ...] | None = None,
              limit: int = 5) -> list[dict]:
    """最近几个作业。前端回到页面时靠它接上没跑完的那个——
    生成本来就在后台线程里跑,不在那一页等着也不会停。"""
    limit = max(1, min(limit, 20))
    sql = ("SELECT id, kind, trip_id, status, done, total, error, created_at, updated_at "
           "FROM ai_jobs WHERE user_id = ?")
    args: list = [user_id]
    if kinds:
        sql += f" AND kind IN ({','.join('?' * len(kinds))})"
        args.extend(kinds)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    return [dict(r) for r in get_db().execute(sql, args).fetchall()]


def cancel(user_id: int, job_id: int) -> bool:
    db = get_db()
    cur = db.execute(
        "UPDATE ai_jobs SET status = 'cancelled', updated_at = ? "
        "WHERE id = ? AND user_id = ? AND status IN ('pending','running')",
        (_now(), job_id, user_id),
    )
    db.commit()
    if not cur.rowcount:
        return False
    with _lock:
        _cancelled.add(job_id)
    return True


def retry(user_id: int, job_id: int, llm: dict | None) -> bool:
    """重跑没成功的部分。

    多步作业里已经 done 的步骤不会重来——那些天的内容用户可能已经改过了,
    重跑就是覆盖。单步作业没有中间状态,整件重跑。
    """
    db = get_db()
    row = db.execute(
        "SELECT kind, input_json, trip_id, status FROM ai_jobs WHERE id = ? AND user_id = ?",
        (job_id, user_id),
    ).fetchone()
    if not row or row["status"] not in _TERMINAL:
        return False
    db.execute("UPDATE ai_jobs SET status = 'pending', error = NULL, updated_at = ? "
               "WHERE id = ?", (_now(), job_id))
    db.commit()
    with _lock:
        _cancelled.discard(job_id)
    try:
        payload = json.loads(row["input_json"] or "{}")
    except (TypeError, ValueError):
        payload = {}
    _start(job_id, user_id, row["kind"], payload, llm, row["trip_id"])
    return True


def cleanup_orphans() -> int:
    """启动时收尸:进程重启会让 pending/running 永远卡住,前端一直转圈。"""
    db = get_db()
    cur = db.execute(
        "UPDATE ai_jobs SET status = 'failed', error = '服务重启,任务中断', "
        "updated_at = ? WHERE status IN ('pending','running')", (_now(),),
    )
    db.commit()
    return cur.rowcount


# ---------- 执行 ----------

def _set(job_id: int, **fields):
    fields["updated_at"] = _now()
    sets = ", ".join(f"{k} = ?" for k in fields)
    db = get_db()
    db.execute(f"UPDATE ai_jobs SET {sets} WHERE id = ?",
               list(fields.values()) + [job_id])
    db.commit()


def _claim(job_id: int) -> bool:
    """把作业从 pending 翻成 running,翻不动就说明轮不到我们跑。

    不能无条件写 running:排队和开跑之间用户可能已经点了取消,直接覆盖会
    把 cancelled 抹掉——然后这一趟照跑不误,最后还卡在 running 出不来。
    """
    db = get_db()
    cur = db.execute(
        "UPDATE ai_jobs SET status = 'running', updated_at = ? "
        "WHERE id = ? AND status = 'pending'", (_now(), job_id))
    db.commit()
    return cur.rowcount > 0


def _run(app, job_id: int, user_id: int, kind: str,
         payload: dict, llm: dict | None, trip_id: int | None) -> None:
    with app.app_context():
        # 配额统计和一部分 handler 直接读 g.user_id,补上,别让它们在
        # worker 里炸掉(routes/chat.py 的图片任务也是这么做的)
        g.user_id = user_id
        ctx = JobCtx(job_id, user_id, kind, payload, llm, trip_id)
        try:
            if not _claim(job_id):
                return
            fn = _RUNNERS.get(kind)
            if not fn:
                _set(job_id, status="failed", error=f"未注册的任务类型:{kind}")
                return
            result = fn(ctx)
            # runner 自己收尾的(取消、分步失败)就别再改状态
            cur = get_db().execute(
                "SELECT status FROM ai_jobs WHERE id = ?", (job_id,)).fetchone()
            if cur and cur["status"] in _TERMINAL:
                return
            _set(job_id, status="done",
                 result_json=json.dumps(result, ensure_ascii=False)
                 if result is not None else None)
        except Exception as e:  # noqa: BLE001
            logger.exception("ai job %s (%s) 失败", job_id, kind)
            try:
                _set(job_id, status="failed", error=str(e)[:300] or "内部错误")
            except Exception:  # noqa: BLE001
                logger.exception("ai job %s 连失败都没记上", job_id)
        finally:
            with _lock:
                _cancelled.discard(job_id)
