"""月度报告路由：列表 / 生成 / 详情 / 本月回顾。"""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, g, jsonify, request

from auth import login_required
from db import get_db
from services.llm_config import current_llm
from services.recap import compute_recap
from services.reports import (
    generate_monthly_report, get_report, get_report_status, list_reports,
)

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/api/reports", methods=["GET"])
@login_required
def api_list_reports():
    return jsonify(list_reports(g.user_id))


@reports_bp.route("/api/reports/generate", methods=["POST"])
@login_required
def api_generate_report():
    data = request.get_json(silent=True) or {}
    period = (request.args.get("month") or data.get("month") or "").strip() or None
    if period and len(period) != 7:
        return jsonify({"error": "month 格式应为 YYYY-MM"}), 400

    llm_cfg = current_llm(data)
    result = generate_monthly_report(g.user_id, period=period, llm=llm_cfg)
    return jsonify(result)


@reports_bp.route("/api/reports/recap", methods=["GET"])
@login_required
def api_recap():
    """本月回顾卡片数据：亮点指标 + 俏皮文案。month 缺省取当月。"""
    period = (request.args.get("month") or "").strip() or datetime.now().strftime("%Y-%m")
    if len(period) != 7:
        return jsonify({"error": "month 格式应为 YYYY-MM"}), 400
    force = str(request.args.get("force") or "").lower() in {"1", "true", "yes", "on"}
    return jsonify(compute_recap(g.user_id, period, llm=current_llm(), force=force))


@reports_bp.route("/api/reports/<period>/status", methods=["GET"])
@login_required
def api_report_status(period: str):
    """异步生成的轻量轮询端点：只返回 status / error_message。"""
    period = period.strip()
    if len(period) != 7:
        return jsonify({"error": "period 格式应为 YYYY-MM"}), 400
    info = get_report_status(g.user_id, period)
    if not info:
        return jsonify({"error": "报告不存在"}), 404
    return jsonify(info)


@reports_bp.route("/api/reports/<period>", methods=["GET"])
@login_required
def api_get_report(period: str):
    period = period.strip()
    if len(period) != 7:
        return jsonify({"error": "period 格式应为 YYYY-MM"}), 400
    report = get_report(g.user_id, period)
    if not report:
        return jsonify({"error": "报告不存在"}), 404
    return jsonify(report)


@reports_bp.route("/api/reports/<period>", methods=["DELETE"])
@login_required
def api_delete_report(period: str):
    period = period.strip()
    db = get_db()
    res = db.execute(
        "DELETE FROM reports WHERE user_id = ? AND period = ?",
        (g.user_id, period),
    )
    db.commit()
    if res.rowcount == 0:
        return jsonify({"error": "报告不存在"}), 404
    return jsonify({"success": True})
