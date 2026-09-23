"""风险测评：拉问卷 + 提交答题。"""
from __future__ import annotations

import json
from flask import g, jsonify, request

from auth import login_required
from db import get_db

from ._common import investment_bp, now_iso, load_llm_cfg


@investment_bp.route("/api/investment/risk-quiz", methods=["GET"])
@login_required
def get_risk_quiz():
    from prompts.investment import RISK_QUIZ_QUESTIONS
    from services.llm import RISK_THRESHOLDS, RISK_MAX_SCORE
    row = get_db().execute(
        "SELECT level, score, summary, updated_at FROM risk_profiles WHERE user_id = ?",
        (g.user_id,),
    ).fetchone()
    return jsonify({
        "questions": RISK_QUIZ_QUESTIONS,
        "profile": dict(row) if row else None,
        "thresholds": {k: list(v) for k, v in RISK_THRESHOLDS.items()},
        "max_score": RISK_MAX_SCORE,
    })


@investment_bp.route("/api/investment/risk-quiz", methods=["POST"])
@login_required
def submit_risk_quiz():
    from services.llm import call_llm_risk_questionnaire
    data = request.get_json() or {}
    answers = data.get("answers") or {}
    if not isinstance(answers, dict) or not answers:
        return jsonify({"error": "缺少答题内容"}), 400

    llm_cfg = load_llm_cfg(data)
    result = call_llm_risk_questionnaire(answers, llm=llm_cfg)

    db = get_db()
    db.execute(
        "INSERT INTO risk_profiles (user_id, level, score, answers_json, summary, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET level=excluded.level, score=excluded.score, "
        "answers_json=excluded.answers_json, summary=excluded.summary, updated_at=excluded.updated_at",
        (g.user_id, result["level"], result["score"],
         json.dumps(answers, ensure_ascii=False), result["summary"], now_iso()),
    )
    db.commit()
    return jsonify(result)
