"""投资顾问对话：general / portfolio / goal 三种 mode。"""
from __future__ import annotations

from flask import g, jsonify, request

from auth import login_required
from services import ai_jobs
from db import get_db
from services.portfolio import (
    build_holding_details, compute_allocation, compute_goal_plan, compute_return,
)

from ._common import investment_bp, fetch_assets, load_llm_cfg


def _build_advisor_context() -> dict:
    db = get_db()
    assets = fetch_assets()
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
    llm_cfg = load_llm_cfg(data)

    if mode == "portfolio":
        assets = fetch_assets()
        if not assets:
            return jsonify({"reply": "请先在资产列表中添加持仓，再查看投资组合分析。"})
        allocation = compute_allocation(assets)
        returns = compute_return(assets)
        holdings = build_holding_details(assets)
        risk_row = get_db().execute(
            "SELECT level FROM risk_profiles WHERE user_id = ?", (g.user_id,),
        ).fetchone()
        risk_level = risk_row["level"] if risk_row else None
        # 再平衡漂移已剥离给独立端点；这里把类型分布 + 每笔持仓交给 LLM 自行点评即可。
        reply = call_llm_portfolio_advice(
            allocation, [], returns, risk_level, llm=llm_cfg, holdings=holdings,
        )
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
            priority=goal.get("priority"),
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


def _run_advisor_reply(ctx) -> dict:
    """投资顾问回复(后台作业)。mode=general 按对话历史回答,mode=portfolio 一键诊断。
    进度和结果走 /api/chat/jobs/<id>,和记账聊天同一套。"""
    from services.llm import stream_advisor_chat, stream_portfolio_advice

    ctx.set_status("思考中…")
    if ctx.payload.get("mode") == "portfolio":
        assets = fetch_assets()
        if not assets:
            text = "请先在资产列表中添加持仓，再查看投资组合分析。"
            ctx.say(text)
            return {"reply": text}
        risk_row = get_db().execute(
            "SELECT level FROM risk_profiles WHERE user_id = ?", (ctx.user_id,),
        ).fetchone()
        pieces = stream_portfolio_advice(
            compute_allocation(assets), [], compute_return(assets),
            risk_row["level"] if risk_row else None, llm=ctx.llm,
            holdings=build_holding_details(assets),
        )
    else:
        pieces = stream_advisor_chat(ctx.payload["history"], context=_build_advisor_context(),
                                     llm=ctx.llm)
    return {"reply": ctx.relay(pieces) or "（空回复）"}


ai_jobs.register("advisor_reply", _run_advisor_reply)


@investment_bp.route("/api/investment/advisor/chat/async", methods=["POST"])
@login_required
def advisor_chat_async():
    """提交一次投资顾问提问,立刻返回 job_id;回复去 /api/chat/jobs/<id> 取。"""
    data = request.get_json(silent=True) or {}
    mode = (data.get("mode") or "general").strip()
    payload: dict = {"mode": mode}
    if mode != "portfolio":
        history = data.get("history") or []
        if not history:
            return jsonify({"error": "history 不能为空"}), 400
        payload["history"] = history[-10:]
    return jsonify({"job_id": ai_jobs.submit(g.user_id, "advisor_reply", payload,
                                             load_llm_cfg(data))}), 202
