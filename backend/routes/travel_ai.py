"""行程 AI 生成的接口。

这里只管**发起**:每个端点排一个作业,立刻返回 job_id。进度、结果、取消、
重试统一走 /api/ai-jobs/*(见 routes/ai_jobs.py)——作业不分行程和非行程,
没必要为它们各留一套轮询端点。

单块生成**一律不落库**:返回的是草稿,前端填进编辑框,由用户改完再保存。
AI 写的东西直接盖掉用户的内容是不能接受的。
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from auth import login_required
from db import get_db
from services import ai_jobs, travel_ai
from services import travel_jobs  # noqa: F401  import 即注册 runner
from services.llm_config import current_llm

travel_ai_bp = Blueprint("travel_ai", __name__)

_MAX_NOTICE = 20000


def _own_trip(trip_id: int):
    return get_db().execute(
        "SELECT * FROM trips WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (trip_id, g.user_id),
    ).fetchone()


@travel_ai_bp.route("/api/trips/ai/extract", methods=["POST"])
@login_required
def ai_extract():
    """从上传的行程单里取出纯文本。

    只抽不生成:文本原样回给前端,用户过目(可以改)之后再点生成。
    旅行社的行程单里常有排版垃圾,让用户先看一眼比直接喂给模型稳。
    """
    from services.doc_text import DocError, extract_text

    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "没有收到文件"}), 400
    try:
        text = extract_text(f.filename, f.read())
    except DocError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"text": text, "chars": len(text), "filename": f.filename})


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
        # 留空 = 交给 AI 按行程气质挑
        "accent": (data.get("accent") or "").strip() or None,
    }
    kind = "import_notice" if notice else "from_idea"
    job_id = ai_jobs.submit(g.user_id, kind, payload, current_llm(data))
    return jsonify({"job_id": job_id}), 201


@travel_ai_bp.route("/api/trips/<int:trip_id>/ai/fill", methods=["POST"])
@login_required
def ai_fill_days(trip_id: int):
    """给已有行程补每天的详情(空着的那些天)。"""
    if not _own_trip(trip_id):
        return jsonify({"error": "行程不存在"}), 404
    data = request.get_json() or {}
    job_id = ai_jobs.submit(
        g.user_id, "fill_days", {"notice": (data.get("notice") or "").strip() or None},
        current_llm(data), trip_id=trip_id,
    )
    return jsonify({"job_id": job_id}), 201


@travel_ai_bp.route("/api/trips/<int:trip_id>/ai/spots", methods=["POST"])
@login_required
def ai_fill_spots(trip_id: int):
    """给已有行程批量补景点介绍。按天分步,只填空的,写过的不动。"""
    if not _own_trip(trip_id):
        return jsonify({"error": "行程不存在"}), 404
    data = request.get_json() or {}
    job_id = ai_jobs.submit(g.user_id, "fill_spots", {}, current_llm(data),
                            trip_id=trip_id)
    return jsonify({"job_id": job_id}), 201


@travel_ai_bp.route("/api/trips/<int:trip_id>/ai/block", methods=["POST"])
@login_required
def ai_block(trip_id: int):
    """单块生成。排一个作业立刻返回 job_id,结果由前端轮询取。

    为什么不同步:慢的时候 LLM 要跑几分钟,HTTP 连接一直挂着会同时踩三个坑——
    nginx 的 proxy_read_timeout、nginx 连续超时后把上游熔断(表现为莫名其妙的
    503)、以及 waitress 默认只有 4 个工作线程被长请求占满。

    结果**不写进行程**:那是给用户改的草稿,直接落库会盖掉人家自己写的。
    """
    if not _own_trip(trip_id):
        return jsonify({"error": "行程不存在"}), 404
    data = request.get_json() or {}
    kind = (data.get("kind") or "").strip()
    if kind not in travel_ai.BLOCK_KINDS:
        return jsonify({"error": f"不支持的生成类型:{kind}"}), 400

    day_no = data.get("day_no")
    if day_no is not None:
        row = get_db().execute(
            "SELECT 1 FROM trip_days WHERE trip_id = ? AND day_no = ?",
            (trip_id, day_no),
        ).fetchone()
        if not row:
            return jsonify({"error": "该天不存在"}), 404
    spot = (data.get("spot") or "").strip()[:80]
    if kind in ("spot_desc", "spot_geo") and not spot:
        return jsonify({"error": "缺少地点名称"}), 400

    job_id = ai_jobs.submit(g.user_id, "block", {
        "kind": kind, "day_no": day_no, "spot": spot or None,
        "hint": (data.get("hint") or "").strip()[:500] or None,
        "label": data.get("label") or kind,
    }, current_llm(data), trip_id=trip_id)
    return jsonify({"job_id": job_id}), 201
