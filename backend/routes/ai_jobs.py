"""后台 AI 作业的状态、取消、重试。

提交在各自的业务端点(/api/decide、/api/checkup/compute、/api/trips/ai/*…),
拿进度和结果统一走这里:行程生成和财务体检在"排队—轮询"这件事上没有
任何区别,不值得各留一套端点。
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from auth import login_required
from services import ai_jobs
from services.llm_config import current_llm

ai_jobs_bp = Blueprint("ai_jobs", __name__)


@ai_jobs_bp.route("/api/ai-jobs", methods=["GET"])
@login_required
def list_jobs():
    """最近的作业。离开页面再回来时用它接上进度——生成在后台跑,
    不会因为关掉那一页就停。

    kinds=a,b 可以只看某几类(比如旅行页只关心自己那几种)。
    """
    raw = (request.args.get("kinds") or "").strip()
    kinds = tuple(k for k in raw.split(",") if k) or None
    try:
        limit = int(request.args.get("limit") or 5)
    except (TypeError, ValueError):
        limit = 5
    return jsonify(ai_jobs.list_jobs(g.user_id, kinds=kinds, limit=limit))


@ai_jobs_bp.route("/api/ai-jobs/<int:job_id>", methods=["GET"])
@login_required
def get_job(job_id: int):
    job = ai_jobs.get(g.user_id, job_id)
    if not job:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify(job)


@ai_jobs_bp.route("/api/ai-jobs/<int:job_id>/cancel", methods=["POST"])
@login_required
def cancel_job(job_id: int):
    if not ai_jobs.get(g.user_id, job_id):
        return jsonify({"error": "任务不存在"}), 404
    return jsonify({"success": ai_jobs.cancel(g.user_id, job_id)})


@ai_jobs_bp.route("/api/ai-jobs/<int:job_id>/retry", methods=["POST"])
@login_required
def retry_job(job_id: int):
    """重跑没成功的部分。多步作业里已经 done 的步骤不会重来——
    那些内容用户可能已经改过了,重跑就是覆盖。"""
    job = ai_jobs.get(g.user_id, job_id)
    if not job:
        return jsonify({"error": "任务不存在"}), 404
    data = request.get_json(silent=True) or {}
    if not ai_jobs.retry(g.user_id, job_id, current_llm(data)):
        return jsonify({"error": "任务还在跑"}), 409
    return jsonify({"job_id": job_id})
