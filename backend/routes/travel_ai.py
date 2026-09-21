"""行程 AI 生成的接口。

两类:
  * 整趟生成(行程单导入 / 一句话想法)—— 多步、耗时,走后台作业 + 轮询
  * 单块生成(某个景点的介绍、某天的贴士…)—— 一次调用就够,同步返回

单块生成**一律不落库**:返回的是草稿,前端填进编辑框,由用户改完再保存。
AI 写的东西直接盖掉用户的内容是不能接受的。
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from auth import login_required
from db import get_db
from services import travel_ai, travel_jobs
from services.llm_config import current_llm

travel_ai_bp = Blueprint("travel_ai", __name__)

_MAX_NOTICE = 20000


def _own_trip(trip_id: int):
    return get_db().execute(
        "SELECT * FROM trips WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (trip_id, g.user_id),
    ).fetchone()


@travel_ai_bp.route("/api/trips/ai/generate", methods=["POST"])
@login_required
def ai_generate():
    """从行程单原文或一句话想法生成一趟新行程。立即返回 job_id。"""
    data = request.get_json() or {}
    notice = (data.get("notice") or "").strip()
    idea = (data.get("idea") or "").strip()
    if not notice and not idea:
        return jsonify({"error": "粘贴行程单原文,或者说一句你想去哪"}), 400
    if len(notice) > _MAX_NOTICE:
        return jsonify({"error": f"行程单太长(超过 {_MAX_NOTICE} 字),请分段导入"}), 400

    payload = {
        "notice": notice or None,
        "idea": idea or None,
        "start_date": (data.get("start_date") or "").strip() or None,
        "end_date": (data.get("end_date") or "").strip() or None,
        "days": data.get("days"),
        "accent": (data.get("accent") or "glacier").strip(),
    }
    kind = "import_notice" if notice else "from_idea"
    job_id = travel_jobs.create_job(g.user_id, kind, payload)
    travel_jobs.start(job_id, g.user_id, current_llm(data))
    return jsonify({"job_id": job_id}), 201


@travel_ai_bp.route("/api/trips/<int:trip_id>/ai/fill", methods=["POST"])
@login_required
def ai_fill_days(trip_id: int):
    """给已有行程补每天的详情(空着的那些天)。"""
    if not _own_trip(trip_id):
        return jsonify({"error": "行程不存在"}), 404
    data = request.get_json() or {}
    job_id = travel_jobs.create_job(
        g.user_id, "fill_days", {"notice": (data.get("notice") or "").strip() or None},
        trip_id=trip_id,
    )
    travel_jobs.start(job_id, g.user_id, current_llm(data))
    return jsonify({"job_id": job_id}), 201


@travel_ai_bp.route("/api/trips/ai/jobs/<int:job_id>", methods=["GET"])
@login_required
def ai_job_status(job_id: int):
    job = travel_jobs.get_job(g.user_id, job_id)
    if not job:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify(job)


@travel_ai_bp.route("/api/trips/ai/jobs/<int:job_id>/cancel", methods=["POST"])
@login_required
def ai_job_cancel(job_id: int):
    if not travel_jobs.get_job(g.user_id, job_id):
        return jsonify({"error": "任务不存在"}), 404
    return jsonify({"success": travel_jobs.cancel_job(g.user_id, job_id)})


@travel_ai_bp.route("/api/trips/ai/jobs/<int:job_id>/retry", methods=["POST"])
@login_required
def ai_job_retry(job_id: int):
    """重跑没成功的步骤。已经 done 的天不会重新生成,不会盖掉你改过的内容。"""
    job = travel_jobs.get_job(g.user_id, job_id)
    if not job:
        return jsonify({"error": "任务不存在"}), 404
    if job["status"] in ("pending", "running"):
        return jsonify({"error": "任务还在跑"}), 409
    db = get_db()
    db.execute("UPDATE trip_ai_jobs SET status = 'pending', error = NULL WHERE id = ?", (job_id,))
    db.commit()
    travel_jobs.start(job_id, g.user_id, current_llm(request.get_json(silent=True) or {}))
    return jsonify({"job_id": job_id})


@travel_ai_bp.route("/api/trips/<int:trip_id>/ai/block", methods=["POST"])
@login_required
def ai_block(trip_id: int):
    """单块生成。同步返回草稿,**不写库**——由用户在编辑框里改完自己保存。"""
    trip = _own_trip(trip_id)
    if not trip:
        return jsonify({"error": "行程不存在"}), 404
    data = request.get_json() or {}
    kind = (data.get("kind") or "").strip()
    if kind not in travel_ai.BLOCK_KINDS:
        return jsonify({"error": f"不支持的生成类型:{kind}"}), 400

    ctx: dict = {"trip": dict(trip), "hint": (data.get("hint") or "").strip() or None}
    day_no = data.get("day_no")
    if day_no is not None:
        row = get_db().execute(
            "SELECT day_no, date, route, transport, meal FROM trip_days "
            "WHERE trip_id = ? AND day_no = ?", (trip_id, day_no),
        ).fetchone()
        if not row:
            return jsonify({"error": "该天不存在"}), 404
        ctx["day"] = dict(row)
    spot = (data.get("spot") or "").strip()
    if spot:
        ctx["spot"] = spot[:80]
    if kind == "spot_desc" and not spot:
        return jsonify({"error": "缺少景点名称"}), 400

    try:
        return jsonify(travel_ai.gen_block(kind, ctx, llm=current_llm(data)))
    except travel_ai.AIError as e:
        return jsonify({"error": str(e)}), 502
