"""投资模块 REST 路由：资产、交易流水、目标、风险测评、顾问对话。"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from flask import Blueprint, g, jsonify, request

from auth import login_required
from cache import invalidate_user
from db import get_db
from services.portfolio import (
    compute_allocation, compute_drift, compute_goal_plan, compute_return,
    compute_top_movers,
)
from services.quotes import get_quote, refresh_user_assets

investment_bp = Blueprint("investment", __name__)

ASSET_TYPES = {"stock", "fund", "bond", "cash", "crypto", "realestate", "other"}
AUTO_PRICED_TYPES = {"stock", "fund"}
TX_KINDS = {"buy", "sell", "dividend", "adjust"}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


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

    symbol = (data.get("symbol") or "").strip() or None
    db = get_db()

    # 股票/基金：如果用户没填市值但给了代码+持仓，尝试自动拉行情
    if atype in AUTO_PRICED_TYPES and symbol and holdings > 0 and current_value <= 0:
        q = get_quote(db, symbol, atype, force=True)
        if q is not None:
            current_value = round(q.price * holdings, 2)

    try:
        cur = db.execute(
            "INSERT INTO assets (user_id, name, type, symbol, holdings, cost_basis, "
            "current_value, currency, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                g.user_id, name, atype, symbol,
                holdings, cost_basis, current_value,
                (data.get("currency") or "CNY").strip() or "CNY",
                (data.get("notes") or "").strip() or None,
                _now(), _now(),
            ),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": f"资产「{name}」已存在，请换个名称或编辑已有资产"}), 409
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
    try:
        db.execute(f"UPDATE assets SET {sets} WHERE id = ? AND user_id = ?", values)
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "资产名称与已有资产重复"}), 409
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
    db = get_db()
    # 仅在显式要求时刷新行情；默认只读组合，避免删除/编辑等操作被网络延迟拖慢
    want_refresh = request.args.get("refresh", "").lower() in {"1", "true", "yes"}
    quote_stats = refresh_user_assets(db, g.user_id) if want_refresh else None
    assets = _fetch_assets()
    allocation = compute_allocation(assets)
    returns = compute_return(assets)
    movers = compute_top_movers(assets)

    risk_row = db.execute(
        "SELECT level FROM risk_profiles WHERE user_id = ?", (g.user_id,),
    ).fetchone()
    risk_level = risk_row["level"] if risk_row else None
    drift = compute_drift(allocation, risk_level=risk_level)

    from services.portfolio import RISK_TARGET_ALLOCATION, DEFAULT_TARGET_ALLOCATION
    target_alloc = RISK_TARGET_ALLOCATION.get(risk_level, DEFAULT_TARGET_ALLOCATION)

    return jsonify({
        "total_value": allocation["total_value"],
        "allocation": allocation,
        "drift": drift,
        "returns": returns,
        "top_movers": movers,
        "risk_level": risk_level,
        "target_allocation": target_alloc,
        "asset_count": len(assets),
        "quotes": quote_stats,
    })


@investment_bp.route("/api/investment/refresh-prices", methods=["POST"])
@login_required
def refresh_prices():
    db = get_db()
    stats = refresh_user_assets(db, g.user_id, force=True)
    invalidate_user(g.user_id)
    return jsonify(stats)


# ===== 聊天 / 图片识别 → 待确认卡片落库 =====

@investment_bp.route("/api/investment/commit-asset", methods=["POST"])
@login_required
def commit_asset():
    """确认把聊天/图片识别得到的资产写入数据库。走与直接新增相同的校验与行情自动同步。"""
    data = request.get_json() or {}
    params = {
        "名称": (data.get("name") or "").strip(),
        "类型": (data.get("type") or "other").strip(),
        "代码": (data.get("symbol") or "").strip(),
        "数量": data.get("holdings") or 0,
        "成本": data.get("cost_basis") or 0,
        "现值": data.get("current_value") or 0,
        "备注": (data.get("notes") or "").strip(),
    }
    from handlers import invest_add_asset
    msg = invest_add_asset(g.user_id, params)
    success = msg.startswith("✅")
    status = 200 if success else (409 if "已存在" in msg else 400)
    return jsonify({"success": success, "message": msg}), status


@investment_bp.route("/api/investment/commit-goal", methods=["POST"])
@login_required
def commit_goal():
    data = request.get_json() or {}
    params = {
        "名称": (data.get("name") or "").strip(),
        "目标金额": data.get("target_amount") or 0,
        "截止日期": (data.get("deadline") or "").strip(),
        "已完成": data.get("current_progress") or 0,
        "优先级": data.get("priority") or 3,
        "备注": (data.get("note") or "").strip(),
    }
    from handlers import invest_add_goal
    msg = invest_add_goal(g.user_id, params)
    success = msg.startswith("✅")
    return jsonify({"success": success, "message": msg}), (200 if success else 400)


@investment_bp.route("/api/investment/parse-image", methods=["POST"])
@login_required
def parse_image():
    """上传持仓/目标截图 → MiniMax 识别 → LLM 工具调用 → 返回待确认卡片。

    复用 /api/chat/image 的识别管线，但把 Prompt 替换为持仓/目标专用指令，
    并限制 tools 为 invest_add_asset / invest_add_goal。
    """
    import base64
    from routes.chat import recognize_image, ALLOWED_IMAGE_TYPES, MAX_IMAGE_SIZE
    from services.llm import call_llm_intent

    if "image" not in request.files:
        return jsonify({"error": "未收到图片文件"}), 400
    file = request.files["image"]
    mime_type = file.content_type
    if mime_type not in ALLOWED_IMAGE_TYPES:
        return jsonify({"error": f"不支持的图片格式：{mime_type}"}), 400
    image_bytes = file.read()
    if len(image_bytes) > MAX_IMAGE_SIZE:
        return jsonify({"error": "图片大小超过 10MB 限制"}), 400

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    recognized = recognize_image(image_b64, mime_type)
    if not recognized:
        return jsonify({"error": "图片识别失败，请重试或手动添加"}), 502

    # 限制只允许投资相关工具
    from tools import FINANCE_TOOLS
    allowed_names = {"invest_add_asset", "invest_add_goal"}
    limited_tools = [t for t in FINANCE_TOOLS if t["function"]["name"] in allowed_names]

    llm_cfg = _load_llm_cfg(request.get_json(silent=True) or {})
    prompt = (
        "[图片识别结果] " + recognized + "\n\n"
        "请根据上面内容判断是"
        "①持仓截图（资产、代码、持仓数量、成本、当前市值、类型）"
        "或 ②理财目标截图（目标名称、目标金额、截止日、优先级）。"
        "对于资产：如果不知道市值请留空由系统自动拉取行情；不要自己编造股票/基金代码。"
        "把识别到的每一条调用 invest_add_asset 或 invest_add_goal。"
    )

    response = call_llm_intent(prompt, llm_cfg, limited_tools)
    pending_assets: list[dict] = []
    pending_goals: list[dict] = []
    reply = None
    if response and "choices" in response:
        msg_obj = response["choices"][0].get("message", {})
        tool_calls = msg_obj.get("tool_calls") or []
        for tc in tool_calls:
            name = tc["function"]["name"]
            try:
                params = json.loads(tc["function"]["arguments"])
            except ValueError:
                continue
            if name == "invest_add_asset":
                n = (params.get("名称") or "").strip()
                if not n:
                    continue
                pending_assets.append({
                    "name": n,
                    "type": (params.get("类型") or "other").strip(),
                    "symbol": (params.get("代码") or "").strip(),
                    "holdings": float(params.get("数量", 0) or 0),
                    "cost_basis": float(params.get("成本", 0) or 0),
                    "current_value": float(params.get("现值", 0) or 0),
                    "notes": (params.get("备注") or "").strip(),
                })
            elif name == "invest_add_goal":
                n = (params.get("名称") or "").strip()
                tgt = float(params.get("目标金额", 0) or 0)
                if not n or tgt <= 0:
                    continue
                pending_goals.append({
                    "name": n,
                    "target_amount": tgt,
                    "deadline": (params.get("截止日期") or "").strip(),
                    "current_progress": float(params.get("已完成", 0) or 0),
                    "priority": int(params.get("优先级", 3) or 3),
                    "note": (params.get("备注") or "").strip(),
                })
        if not tool_calls:
            reply = msg_obj.get("content")

    summary_parts = []
    if pending_assets:
        summary_parts.append(f"识别到 {len(pending_assets)} 项资产")
    if pending_goals:
        summary_parts.append(f"识别到 {len(pending_goals)} 项理财目标")
    if not summary_parts:
        reply = reply or "未能识别出可录入的资产或目标，请检查图片或手动添加。"
    else:
        reply = "；".join(summary_parts) + "，请在下方卡片中核对并确认入库。"

    return jsonify({
        "reply": reply,
        "recognized": recognized,
        "pending_assets": pending_assets,
        "pending_goals": pending_goals,
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
