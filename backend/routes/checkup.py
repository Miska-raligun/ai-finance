"""财务体检路由：计算并存档 / 取某月结果 / 历史趋势。"""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, g, jsonify, request

from auth import login_required
from services.checkup import compute_checkup, get_checkup, get_checkup_history
from services.llm_config import get_llm_config

checkup_bp = Blueprint("checkup", __name__)


def _load_llm_cfg(data: dict) -> dict:
    cfg = dict(data.get("llm") or {})
    for k, v in (get_llm_config(g.user_id) or {}).items():
        cfg.setdefault(k, v)
    return cfg


def _norm_period(raw: str | None) -> str | None:
    period = (raw or "").strip() or datetime.now().strftime("%Y-%m")
    return period if len(period) == 7 else None


@checkup_bp.route("/api/checkup/compute", methods=["POST"])
@login_required
def api_compute():
    data = request.get_json(silent=True) or {}
    period = _norm_period(request.args.get("month") or data.get("month"))
    if not period:
        return jsonify({"error": "month 格式应为 YYYY-MM"}), 400
    return jsonify(compute_checkup(g.user_id, period, llm=_load_llm_cfg(data)))


@checkup_bp.route("/api/checkup/current", methods=["GET"])
@login_required
def api_current():
    period = _norm_period(request.args.get("month"))
    if not period:
        return jsonify({"error": "month 格式应为 YYYY-MM"}), 400
    return jsonify(get_checkup(g.user_id, period) or {})


@checkup_bp.route("/api/checkup/history", methods=["GET"])
@login_required
def api_history():
    try:
        months = int(request.args.get("months") or 12)
    except (TypeError, ValueError):
        months = 12
    months = max(1, min(36, months))
    return jsonify(get_checkup_history(g.user_id, months))
