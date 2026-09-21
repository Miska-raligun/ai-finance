"""行程 AI 生成的后台作业:骨架 → 建行程 → 逐天细化。

和月报那套异步生成同一个思路:立刻返回 job_id,前端轮询进度。
区别是这里有很多步,每步的成败单独记——失败只重跑那一天,不用整趟重来。
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import db as db_module              # 按模块取 DB_FILE,不能按值 import(见 _conn)
from db import get_db
from services import travel_ai

logger = logging.getLogger(__name__)

_EXECUTOR = ThreadPoolExecutor(
    max_workers=int(os.getenv("TRAVEL_AI_WORKERS", "2")),
    thread_name_prefix="travel-ai",
)
_cancelled: set[int] = set()
_lock = threading.Lock()

_DATE_FMT = "%Y-%m-%d"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _conn():
    """后台线程用独立连接。DB_FILE 必须运行时取:按值 import 会把路径
    定死在模块第一次被加载的那一刻,测试里每个用例换库就会连错。"""
    c = sqlite3.connect(db_module.DB_FILE, timeout=15)
    c.row_factory = sqlite3.Row
    return c


# ---------- 作业记录 ----------

def create_job(user_id: int, kind: str, payload: dict, *, trip_id: int | None = None) -> int:
    db = get_db()
    now = _now()
    cur = db.execute(
        "INSERT INTO trip_ai_jobs (user_id, trip_id, kind, status, input_json, "
        "steps_json, done, total, created_at, updated_at) "
        "VALUES (?,?,?,'pending',?,'[]',0,0,?,?)",
        (user_id, trip_id, kind, json.dumps(payload, ensure_ascii=False), now, now),
    )
    db.commit()
    return cur.lastrowid


def get_job(user_id: int, job_id: int) -> dict | None:
    row = get_db().execute(
        "SELECT * FROM trip_ai_jobs WHERE id = ? AND user_id = ?", (job_id, user_id),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d.pop("input_json", None)          # 原文可能很长,轮询不用回传
    try:
        d["steps"] = json.loads(d.pop("steps_json") or "[]")
    except (TypeError, ValueError):
        d["steps"] = []
    return d


def cancel_job(user_id: int, job_id: int) -> bool:
    db = get_db()
    cur = db.execute(
        "UPDATE trip_ai_jobs SET status = 'cancelled', updated_at = ? "
        "WHERE id = ? AND user_id = ? AND status IN ('pending','running')",
        (_now(), job_id, user_id),
    )
    db.commit()
    if cur.rowcount:
        with _lock:
            _cancelled.add(job_id)
        return True
    return False


def cleanup_orphans() -> int:
    """启动时收尸:进程重启会让 pending/running 永远卡住,前端一直转圈。"""
    db = get_db()
    cur = db.execute(
        "UPDATE trip_ai_jobs SET status = 'failed', error = '服务重启,任务中断', "
        "updated_at = ? WHERE status IN ('pending','running')", (_now(),),
    )
    db.commit()
    return cur.rowcount


def _is_cancelled(conn, job_id: int) -> bool:
    with _lock:
        if job_id in _cancelled:
            return True
    row = conn.execute("SELECT status FROM trip_ai_jobs WHERE id = ?", (job_id,)).fetchone()
    return bool(row and row["status"] == "cancelled")


def _update(conn, job_id: int, **fields):
    fields["updated_at"] = _now()
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE trip_ai_jobs SET {sets} WHERE id = ?",
                 list(fields.values()) + [job_id])
    conn.commit()


def _set_steps(conn, job_id: int, steps: list):
    done = sum(1 for s in steps if s["status"] in ("done", "failed", "skipped"))
    _update(conn, job_id, steps_json=json.dumps(steps, ensure_ascii=False),
            done=done, total=len(steps))


# ---------- 执行 ----------

def start(job_id: int, user_id: int, llm: dict | None) -> None:
    _EXECUTOR.submit(_run, job_id, user_id, llm)


def _run(job_id: int, user_id: int, llm: dict | None) -> None:
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM trip_ai_jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return
        payload = json.loads(row["input_json"] or "{}")
        _update(conn, job_id, status="running")

        trip_id = row["trip_id"]
        notice = payload.get("notice")

        if trip_id is None:
            trip_id = _step_outline(conn, job_id, user_id, payload, llm)
            if trip_id is None:
                return

        _step_days(conn, job_id, user_id, trip_id, notice, llm)

        if not _is_cancelled(conn, job_id):
            _update(conn, job_id, status="done")
    except travel_ai.AIError as e:
        logger.warning("travel ai job %s failed: %s", job_id, e)
        _update(conn, job_id, status="failed", error=str(e)[:300])
    except Exception as e:  # noqa: BLE001
        logger.exception("travel ai job %s crashed", job_id)
        _update(conn, job_id, status="failed", error=f"内部错误:{e}"[:300])
    finally:
        with _lock:
            _cancelled.discard(job_id)
        conn.close()


def _step_outline(conn, job_id: int, user_id: int, payload: dict, llm) -> int | None:
    steps = [{"key": "outline", "label": "整理行程骨架", "status": "running", "error": None}]
    _set_steps(conn, job_id, steps)
    try:
        outline = travel_ai.gen_outline(
            notice=payload.get("notice"), idea=payload.get("idea"),
            start=payload.get("start_date"), end=payload.get("end_date"),
            days=payload.get("days"), llm=llm,
        )
    except travel_ai.AIError as e:
        steps[0].update(status="failed", error=str(e)[:200])
        _set_steps(conn, job_id, steps)
        _update(conn, job_id, status="failed", error=str(e)[:300])
        return None

    now = _now()
    accent = payload.get("accent") or "glacier"
    cur = conn.execute(
        "INSERT INTO trips (user_id, title, subtitle, code, start_date, end_date, "
        "accent, cover_note, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (user_id, outline["title"], outline["subtitle"], outline["code"],
         outline["start_date"], outline["end_date"], accent, None, now, now),
    )
    trip_id = cur.lastrowid
    for d in outline["days"]:
        conn.execute(
            "INSERT INTO trip_days (trip_id, user_id, day_no, date, route, transport, "
            "meal, detail_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,'{}',?,?)",
            (trip_id, user_id, d["day_no"], d["date"], d["route"],
             d["transport"], d["meal"], now, now),
        )
    conn.commit()

    steps[0].update(status="done")
    steps.extend({
        "key": f"day-{d['day_no']}",
        "label": f"第 {d['day_no']} 天 · {d['route'] or d['date']}",
        "status": "pending", "error": None,
    } for d in outline["days"])
    _set_steps(conn, job_id, steps)
    _update(conn, job_id, trip_id=trip_id)
    return trip_id


def _step_days(conn, job_id: int, user_id: int, trip_id: int,
               notice: str | None, llm) -> None:
    trip = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    if not trip:
        return
    trip = dict(trip)

    raw = conn.execute("SELECT steps_json FROM trip_ai_jobs WHERE id = ?", (job_id,)).fetchone()
    steps = json.loads(raw["steps_json"] or "[]")
    if not any(s["key"].startswith("day-") for s in steps):
        rows = conn.execute(
            "SELECT day_no, date, route FROM trip_days WHERE trip_id = ? ORDER BY day_no",
            (trip_id,),
        ).fetchall()
        steps = [{"key": f"day-{r['day_no']}",
                  "label": f"第 {r['day_no']} 天 · {r['route'] or r['date']}",
                  "status": "pending", "error": None} for r in rows]
        _set_steps(conn, job_id, steps)

    for step in steps:
        if not step["key"].startswith("day-") or step["status"] == "done":
            continue
        if _is_cancelled(conn, job_id):
            for s in steps:
                if s["status"] in ("pending", "running"):
                    s["status"] = "skipped"
            _set_steps(conn, job_id, steps)
            return

        day_no = int(step["key"].split("-")[1])
        drow = conn.execute(
            "SELECT * FROM trip_days WHERE trip_id = ? AND day_no = ?", (trip_id, day_no),
        ).fetchone()
        if not drow:
            step.update(status="skipped")
            _set_steps(conn, job_id, steps)
            continue

        step.update(status="running", error=None)
        _set_steps(conn, job_id, steps)
        day = dict(drow)
        try:
            detail = travel_ai.gen_day_detail(
                trip, day, travel_ai.slice_notice(notice, day) if notice else None, llm=llm)
            conn.execute(
                "UPDATE trip_days SET detail_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(detail, ensure_ascii=False), _now(), day["id"]),
            )
            conn.commit()
            step.update(status="done")
        except travel_ai.AIError as e:
            # 单天失败不拖垮整趟,记下来让用户重试这一天
            step.update(status="failed", error=str(e)[:200])
        _set_steps(conn, job_id, steps)
