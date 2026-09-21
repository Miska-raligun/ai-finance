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
    try:
        d["result"] = json.loads(d.pop("result_json") or "null")
    except (TypeError, ValueError):
        d["result"] = None
    return d


def list_jobs(user_id: int, *, limit: int = 5) -> list[dict]:
    """最近几个任务。前端回到页面时靠它接上没跑完的那个——
    生成本来就在后台线程里跑,不在这一页等着也不会停。"""
    rows = get_db().execute(
        "SELECT id, trip_id, kind, status, done, total, error, created_at, updated_at "
        "FROM trip_ai_jobs WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, max(1, min(limit, 20))),
    ).fetchall()
    return [dict(r) for r in rows]


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

        if row["kind"] == "block":
            _step_block(conn, job_id, trip_id, payload, llm)
            return

        if row["kind"] == "fill_spots":
            _step_spot_descs(conn, job_id, trip_id, llm)
            if not _is_cancelled(conn, job_id):
                _update(conn, job_id, status="done")
            return

        if trip_id is None:
            trip_id = _step_outline(conn, job_id, user_id, payload, llm)
            if trip_id is None:
                return

        _step_days(conn, job_id, user_id, trip_id, notice, llm)
        _step_extras(conn, job_id, user_id, trip_id, notice, llm)

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
    # 用户显式选了就听用户的;没选(前端传"自动")就用模型按行程气质挑的
    accent = payload.get("accent") or outline.get("accent") or "glacier"
    cur = conn.execute(
        "INSERT INTO trips (user_id, title, subtitle, code, start_date, end_date, "
        "accent, cover_note, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (user_id, outline["title"], outline["subtitle"], outline["code"],
         outline["start_date"], outline["end_date"], accent,
         outline.get("cover_note"), now, now),
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
    if payload.get("notice"):
        # 领队电话、航班号这类只有行程单原文才有,所以这一步只在导入时排
        steps.append({"key": "facts", "label": "抽取速查信息", "status": "pending", "error": None})
    steps.append({"key": "packing", "label": "拟一份打包清单", "status": "pending", "error": None})
    _set_steps(conn, job_id, steps)
    _update(conn, job_id, trip_id=trip_id)
    return trip_id


def _step_block(conn, job_id: int, trip_id: int, payload: dict, llm) -> None:
    """单块生成:一次调用,结果存 result_json 等前端来取。

    **不落库到行程**——这是给用户改的草稿,直接写进去会盖掉人家自己写的。
    """
    steps = [{"key": "block", "label": payload.get("label") or "生成中",
              "status": "running", "error": None}]
    _set_steps(conn, job_id, steps)

    trip = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    if not trip:
        _update(conn, job_id, status="failed", error="行程不存在")
        return

    ctx: dict = {"trip": dict(trip), "hint": payload.get("hint") or None}
    day_no = payload.get("day_no")
    if day_no is not None:
        drow = conn.execute(
            "SELECT day_no, date, route, transport, meal FROM trip_days "
            "WHERE trip_id = ? AND day_no = ?", (trip_id, day_no),
        ).fetchone()
        if drow:
            ctx["day"] = dict(drow)
    if payload.get("spot"):
        ctx["spot"] = payload["spot"]

    try:
        result = travel_ai.gen_block(payload["kind"], ctx, llm=llm)
    except travel_ai.AIError as e:
        steps[0].update(status="failed", error=str(e)[:200])
        _set_steps(conn, job_id, steps)
        _update(conn, job_id, status="failed", error=str(e)[:300])
        return

    steps[0].update(status="done")
    _set_steps(conn, job_id, steps)
    _update(conn, job_id, status="done",
            result_json=json.dumps(result, ensure_ascii=False))


def _missing_desc(detail: dict) -> list[str]:
    """这一天里还没有介绍的地点名(去重、保序)。"""
    out, seen = [], set()
    for st in (detail.get("stops") or []):
        if not isinstance(st, dict):
            continue
        name = (st.get("t") or "").strip()
        if not name or name in seen:
            continue
        if (st.get("desc") or "").strip():
            continue
        seen.add(name)
        out.append(name)
    return out


def _step_spot_descs(conn, job_id: int, trip_id: int, llm) -> None:
    """给已有行程批量补景点介绍。**只填空的**,写过的一律不动。"""
    trip = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    if not trip:
        return
    trip = dict(trip)

    raw = conn.execute("SELECT steps_json FROM trip_ai_jobs WHERE id = ?", (job_id,)).fetchone()
    steps = json.loads(raw["steps_json"] or "[]")
    days = [dict(r) for r in conn.execute(
        "SELECT * FROM trip_days WHERE trip_id = ? ORDER BY day_no", (trip_id,),
    ).fetchall()]

    if not steps:
        steps = []
        for d in days:
            try:
                detail = json.loads(d["detail_json"] or "{}")
            except (TypeError, ValueError):
                continue
            todo = _missing_desc(detail)
            if todo:
                steps.append({"key": f"spots-{d['day_no']}",
                              "label": f"第 {d['day_no']} 天 · {len(todo)} 个地点",
                              "status": "pending", "error": None})
        _set_steps(conn, job_id, steps)
        if not steps:
            return

    by_no = {d["day_no"]: d for d in days}
    for step in steps:
        if step["status"] == "done" or not step["key"].startswith("spots-"):
            continue
        if _is_cancelled(conn, job_id):
            for s2 in steps:
                if s2["status"] in ("pending", "running"):
                    s2["status"] = "skipped"
            _set_steps(conn, job_id, steps)
            return

        day = by_no.get(int(step["key"].split("-")[1]))
        if not day:
            step.update(status="skipped")
            _set_steps(conn, job_id, steps)
            continue

        step.update(status="running", error=None)
        _set_steps(conn, job_id, steps)
        try:
            detail = json.loads(day["detail_json"] or "{}")
            names = _missing_desc(detail)
            if not names:
                step.update(status="skipped")
                _set_steps(conn, job_id, steps)
                continue
            got = travel_ai.gen_spot_descs(trip, day, names, llm=llm)
            written = 0
            for st in (detail.get("stops") or []):
                if not isinstance(st, dict):
                    continue
                name = (st.get("t") or "").strip()
                # 再判一次空:用户可能在任务跑的当口自己写了一条
                if name in got and not (st.get("desc") or "").strip():
                    st["desc"] = got[name]
                    written += 1
            if written:
                conn.execute(
                    "UPDATE trip_days SET detail_json = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(detail, ensure_ascii=False), _now(), day["id"]),
                )
                conn.commit()
            step.update(status="done" if written else "skipped")
        except travel_ai.AIError as e:
            step.update(status="failed", error=str(e)[:200])
        _set_steps(conn, job_id, steps)


def _step_extras(conn, job_id: int, user_id: int, trip_id: int,
                 notice: str | None, llm) -> None:
    """速查 + 打包。两者都只在表为空时写——不覆盖用户已经整理好的内容。"""
    raw = conn.execute("SELECT steps_json FROM trip_ai_jobs WHERE id = ?", (job_id,)).fetchone()
    steps = json.loads(raw["steps_json"] or "[]")
    trip = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    if not trip:
        return
    trip = dict(trip)

    for step in steps:
        if step["key"] not in ("facts", "packing") or step["status"] == "done":
            continue
        if _is_cancelled(conn, job_id):
            return
        step.update(status="running", error=None)
        _set_steps(conn, job_id, steps)
        try:
            if step["key"] == "facts":
                n = _fill_facts(conn, user_id, trip_id, notice, llm)
            else:
                n = _fill_packing(conn, user_id, trip_id, trip, llm)
            step.update(status="done" if n else "skipped")
        except travel_ai.AIError as e:
            step.update(status="failed", error=str(e)[:200])
        _set_steps(conn, job_id, steps)


def _fill_facts(conn, user_id: int, trip_id: int, notice: str | None, llm) -> int:
    if not notice:
        return 0
    if conn.execute("SELECT COUNT(*) FROM trip_facts WHERE trip_id = ?",
                    (trip_id,)).fetchone()[0]:
        return 0
    items = travel_ai.extract_facts(notice, llm=llm)
    now = _now()
    for i, it in enumerate(items):
        # is_public 一律 0:里面可能有领队手机号,是第三方个人信息,
        # 要不要跟着分享链接出去由本人逐条决定
        conn.execute(
            "INSERT INTO trip_facts (trip_id, user_id, label, body, is_public, sort_order, "
            "created_at, updated_at) VALUES (?,?,?,?,0,?,?,?)",
            (trip_id, user_id, it["label"], it["body"], i, now, now),
        )
    conn.commit()
    return len(items)


def _fill_packing(conn, user_id: int, trip_id: int, trip: dict, llm) -> int:
    if conn.execute("SELECT COUNT(*) FROM trip_pack_items WHERE trip_id = ?",
                    (trip_id,)).fetchone()[0]:
        return 0
    got = travel_ai.gen_block("packing", {"trip": trip}, llm=llm)
    items = got.get("items") or []
    for i, it in enumerate(items):
        conn.execute(
            "INSERT INTO trip_pack_items (trip_id, user_id, grp, label, hint, checked, "
            "sort_order) VALUES (?,?,?,?,?,0,?)",
            (trip_id, user_id, it.get("grp"), it["label"], it.get("hint"), i),
        )
    conn.commit()
    return len(items)


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
