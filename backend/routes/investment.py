"""投资模块 REST 路由：资产、交易流水、目标、风险测评、顾问对话。"""
from __future__ import annotations

import json
from datetime import datetime

from flask import Blueprint, g, jsonify, request

from auth import login_required
from cache import invalidate_user
from db import get_db
from services.portfolio import (
    compute_allocation, compute_drift, compute_goal_plan, compute_return,
    compute_top_movers,
)

investment_bp = Blueprint("investment", __name__)

ASSET_TYPES = {"stock", "fund", "bond", "cash", "crypto", "realestate", "other"}
TX_KINDS = {"buy", "sell", "dividend", "adjust"}


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


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


def _fetch_assets() -> list[dict]:
    rows = get_db().execute(
        "SELECT id, name, type, symbol, holdings, cost_basis, current_value, "
        "currency, notes, created_at, updated_at FROM assets WHERE user_id = ? "
        "ORDER BY current_value DESC",
        (g.user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ===== 资产 CRUD =====

@investment_bp.route("/api/investment/assets", methods=["GET"])
@login_required
def list_assets():
    return jsonify(_fetch_assets())


@investment_bp.route("/api/investment/assets", methods=["POST"])
@login_required
def create_asset():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    atype = (data.get("type") or "other").strip()
    if not name:
        return jsonify({"error": "缺少资产名称"}), 400
    if atype not in ASSET_TYPES:
        return jsonify({"error": f"非法资产类型：{atype}"}), 400
    try:
        holdings = float(data.get("holdings") or 0)
        cost_basis = float(data.get("cost_basis") or 0)
        current_value = float(data.get("current_value") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "数值字段必须为数字"}), 400

    db = get_db()
    cur = db.execute(
        "INSERT INTO assets (user_id, name, type, symbol, holdings, cost_basis, "
        "current_value, currency, notes, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            g.user_id, name, atype, (data.get("symbol") or "").strip() or None,
            holdings, cost_basis, current_value,
            (data.get("currency") or "CNY").strip() or "CNY",
            (data.get("notes") or "").strip() or None,
            _now(), _now(),
        ),
    )
    db.commit()
    invalidate_user(g.user_id)
    return jsonify({"id": cur.lastrowid, "success": True}), 201


@investment_bp.route("/api/investment/assets/<int:asset_id>", methods=["PATCH"])
@login_required
def update_asset(asset_id: int):
    data = request.get_json() or {}
    db = get_db()
    row = db.execute(
        "SELECT id FROM assets WHERE id = ? AND user_id = ?", (asset_id, g.user_id),
    ).fetchone()
    if not row:
        return jsonify({"error": "资产不存在"}), 404

    allowed = {"name", "type", "symbol", "holdings", "cost_basis", "current_value", "currency", "notes"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({"error": "无可更新字段"}), 400
    if "type" in updates and updates["type"] not in ASSET_TYPES:
        return jsonify({"error": "非法资产类型"}), 400

    sets = ", ".join(f"{k} = ?" for k in updates) + ", updated_at = ?"
    values = list(updates.values()) + [_now(), asset_id, g.user_id]
    db.execute(f"UPDATE assets SET {sets} WHERE id = ? AND user_id = ?", values)
    db.commit()
    invalidate_user(g.user_id)
    return jsonify({"success": True})


@investment_bp.route("/api/investment/assets/<int:asset_id>", methods=["DELETE"])
@login_required
def delete_asset(asset_id: int):
    db = get_db()
    res = db.execute(
        "DELETE FROM assets WHERE id = ? AND user_id = ?", (asset_id, g.user_id),
    )
    db.execute(
        "DELETE FROM asset_transactions WHERE asset_id = ? AND user_id = ?",
        (asset_id, g.user_id),
    )
    db.commit()
    invalidate_user(g.user_id)
    if res.rowcount == 0:
        return jsonify({"error": "资产不存在"}), 404
    return jsonify({"success": True})


# ===== 交易流水 =====

@investment_bp.route("/api/investment/transactions", methods=["GET"])
@login_required
def list_transactions():
    asset_id = request.args.get("asset_id")
    db = get_db()
    if asset_id:
        rows = db.execute(
            "SELECT * FROM asset_transactions WHERE user_id = ? AND asset_id = ? "
            "ORDER BY date DESC, id DESC",
            (g.user_id, asset_id),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM asset_transactions WHERE user_id = ? "
            "ORDER BY date DESC, id DESC LIMIT 100",
            (g.user_id,),
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@investment_bp.route("/api/investment/transactions", methods=["POST"])
@login_required
def add_transaction():
    data = request.get_json() or {}
    try:
        asset_id = int(data.get("asset_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "缺少 asset_id"}), 400
    kind = (data.get("kind") or "").strip()
    if kind not in TX_KINDS:
        return jsonify({"error": f"非法交易类型：{kind}"}), 400
    try:
        quantity = float(data.get("quantity") or 0)
        price = float(data.get("price") or 0)
        fee = float(data.get("fee") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "数值字段必须为数字"}), 400
    date = (data.get("date") or datetime.now().strftime("%Y-%m-%d")).strip()

    db = get_db()
    owns = db.execute(
        "SELECT id FROM assets WHERE id = ? AND user_id = ?", (asset_id, g.user_id),
    ).fetchone()
    if not owns:
        return jsonify({"error": "资产不存在"}), 404

    db.execute(
        "INSERT INTO asset_transactions (user_id, asset_id, kind, quantity, price, fee, date, note, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (g.user_id, asset_id, kind, quantity, price, fee, date,
         (data.get("note") or "").strip() or None, _now()),
    )
    db.commit()
    invalidate_user(g.user_id)
    return jsonify({"success": True}), 201


# ===== 投资组合概览 =====

@investment_bp.route("/api/investment/portfolio", methods=["GET"])
@login_required
def portfolio_summary():
    assets = _fetch_assets()
    allocation = compute_allocation(assets)
    returns = compute_return(assets)
    movers = compute_top_movers(assets)

    risk_row = get_db().execute(
        "SELECT level FROM risk_profiles WHERE user_id = ?", (g.user_id,),
    ).fetchone()
    risk_level = risk_row["level"] if risk_row else None
    drift = compute_drift(allocation, risk_level=risk_level)

    return jsonify({
        "total_value": allocation["total_value"],
        "allocation": allocation,
        "drift": drift,
        "returns": returns,
        "top_movers": movers,
        "risk_level": risk_level,
        "asset_count": len(assets),
    })


# ===== 目标 CRUD =====

@investment_bp.route("/api/investment/goals", methods=["GET"])
@login_required
def list_goals():
    rows = get_db().execute(
        "SELECT * FROM financial_goals WHERE user_id = ? ORDER BY priority ASC, deadline ASC",
        (g.user_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@investment_bp.route("/api/investment/goals", methods=["POST"])
@login_required
def create_goal():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "缺少目标名称"}), 400
    try:
        target = float(data.get("target_amount") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "target_amount 必须为数字"}), 400
    if target <= 0:
        return jsonify({"error": "target_amount 必须大于 0"}), 400

    db = get_db()
    cur = db.execute(
        "INSERT INTO financial_goals (user_id, name, target_amount, deadline, "
        "current_progress, priority, note, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            g.user_id, name, target,
            (data.get("deadline") or "").strip() or None,
            float(data.get("current_progress") or 0),
            int(data.get("priority") or 3),
            (data.get("note") or "").strip() or None,
            _now(), _now(),
        ),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid, "success": True}), 201


@investment_bp.route("/api/investment/goals/<int:goal_id>", methods=["PATCH"])
@login_required
def update_goal(goal_id: int):
    data = request.get_json() or {}
    allowed = {"name", "target_amount", "deadline", "current_progress", "priority", "note"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({"error": "无可更新字段"}), 400

    db = get_db()
    res = db.execute(
        "SELECT id FROM financial_goals WHERE id = ? AND user_id = ?",
        (goal_id, g.user_id),
    ).fetchone()
    if not res:
        return jsonify({"error": "目标不存在"}), 404

    sets = ", ".join(f"{k} = ?" for k in updates) + ", updated_at = ?"
    values = list(updates.values()) + [_now(), goal_id, g.user_id]
    db.execute(f"UPDATE financial_goals SET {sets} WHERE id = ? AND user_id = ?", values)
    db.commit()
    return jsonify({"success": True})


@investment_bp.route("/api/investment/goals/<int:goal_id>", methods=["DELETE"])
@login_required
def delete_goal(goal_id: int):
    db = get_db()
    res = db.execute(
        "DELETE FROM financial_goals WHERE id = ? AND user_id = ?",
        (goal_id, g.user_id),
    )
    db.commit()
    if res.rowcount == 0:
        return jsonify({"error": "目标不存在"}), 404
    return jsonify({"success": True})


# ===== 风险测评 =====

@investment_bp.route("/api/investment/risk-quiz", methods=["GET"])
@login_required
def get_risk_quiz():
    from prompts.investment import RISK_QUIZ_QUESTIONS
    row = get_db().execute(
        "SELECT level, score, summary, updated_at FROM risk_profiles WHERE user_id = ?",
        (g.user_id,),
    ).fetchone()
    return jsonify({
        "questions": RISK_QUIZ_QUESTIONS,
        "profile": dict(row) if row else None,
    })


@investment_bp.route("/api/investment/risk-quiz", methods=["POST"])
@login_required
def submit_risk_quiz():
    from services.llm import call_llm_risk_questionnaire
    data = request.get_json() or {}
    answers = data.get("answers") or {}
    if not isinstance(answers, dict) or not answers:
        return jsonify({"error": "缺少答题内容"}), 400

    llm_cfg = _load_llm_cfg(data)
    result = call_llm_risk_questionnaire(answers, llm=llm_cfg)

    db = get_db()
    db.execute(
        "INSERT INTO risk_profiles (user_id, level, score, answers_json, summary, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET level=excluded.level, score=excluded.score, "
        "answers_json=excluded.answers_json, summary=excluded.summary, updated_at=excluded.updated_at",
        (g.user_id, result["level"], result["score"],
         json.dumps(answers, ensure_ascii=False), result["summary"], _now()),
    )
    db.commit()
    return jsonify(result)


# ===== 投资顾问对话 =====

def _build_advisor_context() -> dict:
    db = get_db()
    assets = _fetch_assets()
    allocation = compute_allocation(assets)
    returns = compute_return(assets)
    goals = [dict(r) for r in db.execute(
        "SELECT name, target_amount, deadline, current_progress FROM financial_goals WHERE user_id = ?",
        (g.user_id,),
    ).fetchall()]
    risk_row = db.execute(
        "SELECT level FROM risk_profiles WHERE user_id = ?", (g.user_id,),
    ).fetchone()
    return {
        "total_value": allocation["total_value"],
        "allocation_by_type": allocation["by_type"],
        "returns": returns,
        "goals": goals,
        "risk_level": risk_row["level"] if risk_row else None,
    }


@investment_bp.route("/api/investment/advisor/chat", methods=["POST"])
@login_required
def advisor_chat():
    from services.llm import call_llm_advisor_chat, call_llm_portfolio_advice, call_llm_goal_plan
    data = request.get_json() or {}
    mode = (data.get("mode") or "general").strip()
    llm_cfg = _load_llm_cfg(data)

    if mode == "portfolio":
        assets = _fetch_assets()
        if not assets:
            return jsonify({"reply": "请先在资产列表中添加持仓，再查看投资组合分析。"})
        allocation = compute_allocation(assets)
        returns = compute_return(assets)
        risk_row = get_db().execute(
            "SELECT level FROM risk_profiles WHERE user_id = ?", (g.user_id,),
        ).fetchone()
        risk_level = risk_row["level"] if risk_row else None
        drift = compute_drift(allocation, risk_level=risk_level)
        reply = call_llm_portfolio_advice(allocation, drift, returns, risk_level, llm=llm_cfg)
        return jsonify({"reply": reply})

    if mode == "goal":
        try:
            goal_id = int(data.get("goal_id"))
        except (TypeError, ValueError):
            return jsonify({"error": "缺少 goal_id"}), 400
        row = get_db().execute(
            "SELECT * FROM financial_goals WHERE id = ? AND user_id = ?",
            (goal_id, g.user_id),
        ).fetchone()
        if not row:
            return jsonify({"error": "目标不存在"}), 404
        goal = dict(row)
        monthly = float(data.get("monthly_net_cashflow") or 0)
        plan = compute_goal_plan(
            goal["target_amount"], goal.get("current_progress") or 0,
            goal.get("deadline"), monthly,
        )
        reply = call_llm_goal_plan(goal, plan, llm=llm_cfg)
        return jsonify({"reply": reply, "plan": plan})

    # general 对话模式
    history = data.get("history") or []
    if not history:
        return jsonify({"error": "history 不能为空"}), 400
    context = _build_advisor_context()
    reply = call_llm_advisor_chat(history, context=context, llm=llm_cfg)
    return jsonify({"reply": reply})
