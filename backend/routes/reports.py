"""月度报告路由：列表 / 生成 / 详情。"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from auth import login_required
from db import get_db
from services.reports import generate_monthly_report, get_report, list_reports

reports_bp = Blueprint("reports", __name__)


def _load_llm_cfg(data: dict) -> dict:
    cfg = dict(data.get("llm") or {})
    row = get_db().execute(
        "SELECT url, apikey, model, persona FROM llm_config WHERE user_id = ?",
        (g.user_id,),
    ).fetchone()
    if row:
        for k, v in dict(row).items():
            cfg.setdefault(k, v)
    return cfg


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

    llm_cfg = _load_llm_cfg(data)
    result = generate_monthly_report(g.user_id, period=period, llm=llm_cfg)
    return jsonify(result)


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
