"""单次 AI 作业的状态查询。

提交在各自的业务端点(/api/decide、/api/checkup/compute…),拿结果统一走这里。
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify

from auth import login_required
from services import ai_jobs

ai_jobs_bp = Blueprint("ai_jobs", __name__)


@ai_jobs_bp.route("/api/ai-jobs/<int:job_id>", methods=["GET"])
@login_required
def get_job(job_id: int):
    job = ai_jobs.get(g.user_id, job_id)
    if not job:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify(job)
