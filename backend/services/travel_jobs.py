"""行程 AI 生成:骨架 → 建行程 → 逐天细化,以及单块生成。

作业本身的排队、状态、取消、重试都在 services/ai_jobs 里,这个模块只写
"每一步怎么干"。多步的意义是每步成败单独记——失败只重跑那一天,
不用整趟重来。

注意 runner 跑在 worker 线程的 app_context 里,所以这里照常用 get_db();
以前这里自己开 sqlite3 连接,是因为作业池和请求不共用 app_context。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from db import get_db
from services import ai_jobs, travel_ai

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _fail(ctx, steps, step, e) -> None:
    """一步挂了:记在这一步上,整个作业也标失败。"""
    step.update(status="failed", error=str(e)[:200])
    ctx.set_steps(steps)
    _set_failed(ctx, str(e))


def _set_failed(ctx, msg: str) -> None:
    db = get_db()
    db.execute("UPDATE ai_jobs SET status = 'failed', error = ?, updated_at = ? "
               "WHERE id = ?", (msg[:300], _now(), ctx.job_id))
    db.commit()


# ---------- 入口:整趟生成 ----------

def run_trip(ctx):
    """import_notice / from_idea / fill_days 共用的主流程。"""
    notice = ctx.payload.get("notice")
    trip_id = ctx.trip_id
    if trip_id is None:
        trip_id = _step_outline(ctx)
        if trip_id is None:
            return None

    _step_days(ctx, trip_id, notice)
    _step_extras(ctx, trip_id, notice)
    return None


def run_spots(ctx):
    """给已有行程批量补景点介绍。"""
    _step_spot_descs(ctx, ctx.trip_id)
    return None


def run_block(ctx):
    """单块生成:一次调用,结果回给前端。

    **不落库到行程**——这是给用户改的草稿,直接写进去会盖掉人家自己写的。
    """
    steps = [{"key": "block", "label": ctx.payload.get("label") or "生成中",
              "status": "running", "error": None}]
    ctx.set_steps(steps)

    trip = get_db().execute("SELECT * FROM trips WHERE id = ?", (ctx.trip_id,)).fetchone()
    if not trip:
        _set_failed(ctx, "行程不存在")
        return None

    blk: dict = {"trip": dict(trip), "hint": ctx.payload.get("hint") or None}
    day_no = ctx.payload.get("day_no")
    if day_no is not None:
        drow = get_db().execute(
            "SELECT day_no, date, route, transport, meal FROM trip_days "
            "WHERE trip_id = ? AND day_no = ?", (ctx.trip_id, day_no),
        ).fetchone()
        if drow:
            blk["day"] = dict(drow)
    if ctx.payload.get("spot"):
        blk["spot"] = ctx.payload["spot"]

    try:
        result = travel_ai.gen_block(ctx.payload["kind"], blk, llm=ctx.llm)
    except travel_ai.AIError as e:
        _fail(ctx, steps, steps[0], e)
        return None

    steps[0].update(status="done")
    ctx.set_steps(steps)
    return result


# ---------- 各步 ----------

def _step_outline(ctx) -> int | None:
    steps = [{"key": "outline", "label": "整理行程骨架", "status": "running", "error": None}]
    ctx.set_steps(steps)
    p = ctx.payload
    try:
        outline = travel_ai.gen_outline(
            notice=p.get("notice"), idea=p.get("idea"),
            start=p.get("start_date"), end=p.get("end_date"),
            days=p.get("days"), llm=ctx.llm,
        )
    except travel_ai.AIError as e:
        _fail(ctx, steps, steps[0], e)
        return None

    db = get_db()
    now = _now()
    # 用户显式选了就听用户的;没选(前端传"自动")就用模型按行程气质挑的
    accent = p.get("accent") or outline.get("accent") or "glacier"
    cur = db.execute(
        "INSERT INTO trips (user_id, title, subtitle, code, start_date, end_date, "
        "accent, cover_note, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (ctx.user_id, outline["title"], outline["subtitle"], outline["code"],
         outline["start_date"], outline["end_date"], accent,
         outline.get("cover_note"), now, now),
    )
    trip_id = cur.lastrowid
    for d in outline["days"]:
        db.execute(
            "INSERT INTO trip_days (trip_id, user_id, day_no, date, route, transport, "
            "meal, detail_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,'{}',?,?)",
            (trip_id, ctx.user_id, d["day_no"], d["date"], d["route"],
             d["transport"], d["meal"], now, now),
        )
    db.commit()

    steps[0].update(status="done")
    steps.extend({
        "key": f"day-{d['day_no']}",
        "label": f"第 {d['day_no']} 天 · {d['route'] or d['date']}",
        "status": "pending", "error": None,
    } for d in outline["days"])
    if p.get("notice"):
        # 领队电话、航班号这类只有行程单原文才有,所以这一步只在导入时排
        steps.append({"key": "facts", "label": "抽取速查信息", "status": "pending", "error": None})
    steps.append({"key": "packing", "label": "拟一份打包清单", "status": "pending", "error": None})
    ctx.set_steps(steps)
    ctx.set_trip(trip_id)
    return trip_id


def _abort_rest(ctx, steps) -> None:
    for s in steps:
        if s["status"] in ("pending", "running"):
            s["status"] = "skipped"
    ctx.set_steps(steps)


def _step_days(ctx, trip_id: int, notice: str | None) -> None:
    db = get_db()
    trow = db.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    if not trow:
        return
    trip = dict(trow)

    steps = ctx.steps
    if not any(s["key"].startswith("day-") for s in steps):
        rows = db.execute(
            "SELECT day_no, date, route FROM trip_days WHERE trip_id = ? ORDER BY day_no",
            (trip_id,),
        ).fetchall()
        steps = [{"key": f"day-{r['day_no']}",
                  "label": f"第 {r['day_no']} 天 · {r['route'] or r['date']}",
                  "status": "pending", "error": None} for r in rows]
        ctx.set_steps(steps)

    for step in steps:
        if not step["key"].startswith("day-") or step["status"] == "done":
            continue
        if ctx.cancelled:
            _abort_rest(ctx, steps)
            return

        day_no = int(step["key"].split("-")[1])
        drow = db.execute(
            "SELECT * FROM trip_days WHERE trip_id = ? AND day_no = ?", (trip_id, day_no),
        ).fetchone()
        if not drow:
            step.update(status="skipped")
            ctx.set_steps(steps)
            continue

        step.update(status="running", error=None)
        ctx.set_steps(steps)
        day = dict(drow)
        try:
            detail = travel_ai.gen_day_detail(
                trip, day, travel_ai.slice_notice(notice, day) if notice else None,
                llm=ctx.llm)
            db.execute(
                "UPDATE trip_days SET detail_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(detail, ensure_ascii=False), _now(), day["id"]),
            )
            db.commit()
            step.update(status="done")
        except travel_ai.AIError as e:
            # 单天失败不拖垮整趟,记下来让用户重试这一天
            step.update(status="failed", error=str(e)[:200])
        ctx.set_steps(steps)


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


def _step_spot_descs(ctx, trip_id: int) -> None:
    """**只填空的**,写过的一律不动。"""
    db = get_db()
    trow = db.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    if not trow:
        return
    trip = dict(trow)

    steps = ctx.steps
    days = [dict(r) for r in db.execute(
        "SELECT * FROM trip_days WHERE trip_id = ? ORDER BY day_no", (trip_id,),
    ).fetchall()]

    if not steps:
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
        ctx.set_steps(steps)
        if not steps:
            return

    by_no = {d["day_no"]: d for d in days}
    for step in steps:
        if step["status"] == "done" or not step["key"].startswith("spots-"):
            continue
        if ctx.cancelled:
            _abort_rest(ctx, steps)
            return

        day = by_no.get(int(step["key"].split("-")[1]))
        if not day:
            step.update(status="skipped")
            ctx.set_steps(steps)
            continue

        step.update(status="running", error=None)
        ctx.set_steps(steps)
        try:
            detail = json.loads(day["detail_json"] or "{}")
            names = _missing_desc(detail)
            if not names:
                step.update(status="skipped")
                ctx.set_steps(steps)
                continue
            got = travel_ai.gen_spot_descs(trip, day, names, llm=ctx.llm)
            missed = [n for n in names if n not in got]
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
                db.execute(
                    "UPDATE trip_days SET detail_json = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(detail, ensure_ascii=False), _now(), day["id"]),
                )
                db.commit()
                step.update(status="done", error=(
                    f"这几个没写成:{'、'.join(missed[:4])}" if missed else None))
            else:
                # 有要写的却一条都没写成,这是失败,不是"没什么可做"。
                # 以前这里也记 skipped,于是任务报"完成",刷新后还是提示
                # 没写介绍,用户点几次都一样,却看不到任何错。
                step.update(status="failed",
                            error=f"这几个地点模型没认出来:{'、'.join(names[:4])}")
        except travel_ai.AIError as e:
            step.update(status="failed", error=str(e)[:200])
        ctx.set_steps(steps)


def _step_extras(ctx, trip_id: int, notice: str | None) -> None:
    """速查 + 打包。两者都只在表为空时写——不覆盖用户已经整理好的内容。"""
    steps = ctx.steps
    trow = get_db().execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    if not trow:
        return
    trip = dict(trow)

    for step in steps:
        if step["key"] not in ("facts", "packing") or step["status"] == "done":
            continue
        if ctx.cancelled:
            return
        step.update(status="running", error=None)
        ctx.set_steps(steps)
        try:
            if step["key"] == "facts":
                n = _fill_facts(ctx.user_id, trip_id, notice, ctx.llm)
            else:
                n = _fill_packing(ctx.user_id, trip_id, trip, ctx.llm)
            step.update(status="done" if n else "skipped")
        except travel_ai.AIError as e:
            step.update(status="failed", error=str(e)[:200])
        ctx.set_steps(steps)


def _fill_facts(user_id: int, trip_id: int, notice: str | None, llm) -> int:
    if not notice:
        return 0
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM trip_facts WHERE trip_id = ?",
                  (trip_id,)).fetchone()[0]:
        return 0
    items = travel_ai.extract_facts(notice, llm=llm)
    now = _now()
    for i, it in enumerate(items):
        # is_public 一律 0:里面可能有领队手机号,是第三方个人信息,
        # 要不要跟着分享链接出去由本人逐条决定
        db.execute(
            "INSERT INTO trip_facts (trip_id, user_id, label, body, is_public, sort_order, "
            "created_at, updated_at) VALUES (?,?,?,?,0,?,?,?)",
            (trip_id, user_id, it["label"], it["body"], i, now, now),
        )
    db.commit()
    return len(items)


def _fill_packing(user_id: int, trip_id: int, trip: dict, llm) -> int:
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM trip_pack_items WHERE trip_id = ?",
                  (trip_id,)).fetchone()[0]:
        return 0
    got = travel_ai.gen_block("packing", {"trip": trip}, llm=llm)
    items = got.get("items") or []
    for i, it in enumerate(items):
        db.execute(
            "INSERT INTO trip_pack_items (trip_id, user_id, grp, label, hint, checked, "
            "sort_order) VALUES (?,?,?,?,?,0,?)",
            (trip_id, user_id, it.get("grp"), it["label"], it.get("hint"), i),
        )
    db.commit()
    return len(items)


# 行程相关的所有作业类型,前端列"最近任务"时按这个筛
KINDS = ("import_notice", "from_idea", "fill_days", "fill_spots", "block")

for _k in ("import_notice", "from_idea", "fill_days"):
    ai_jobs.register(_k, run_trip)
ai_jobs.register("fill_spots", run_spots)
ai_jobs.register("block", run_block)
