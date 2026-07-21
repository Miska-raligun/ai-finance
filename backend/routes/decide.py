"""购前决策助手 — 用户输入「想买什么 + 价格」，结合个人财务上下文给出建议。

区别于通用 ChatGPT 的关键：把用户最近 3 个月的支出趋势 / 当月预算余量 /
储蓄目标进度作为 system context 喂给 LLM，建议才真正"个性化"。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request

from auth import login_required
from constants import LLM_TIMEOUT_LONG
from db import get_db
from services.llm import _call_llm
from services.llm_config import current_llm

decide_bp = Blueprint("decide", __name__)
logger = logging.getLogger(__name__)


def _gather_context(user_id: int) -> dict:
    """采集决策所需的财务画像：近 3 月支出、本月预算余量、储蓄目标、近 30 天净流入。"""
    db = get_db()
    today = datetime.now().date()
    cur_month = today.strftime("%Y-%m")
    three_mo_start = (today.replace(day=1) - timedelta(days=90)).strftime("%Y-%m-%d")

    # 近 3 个月支出（按分类）
    rows = db.execute(
        "SELECT category, SUM(amount) AS total "
        "FROM records WHERE user_id = ? AND date >= ? "
        "AND deleted_at IS NULL "
        "GROUP BY category ORDER BY total DESC LIMIT 8",
        (user_id, three_mo_start),
    ).fetchall()
    by_cat = [{"category": r["category"], "total": round(r["total"], 2)} for r in rows]
    total_3m = sum(r["total"] for r in by_cat)

    # 本月已花
    month_spend = db.execute(
        "SELECT COALESCE(SUM(amount), 0) AS s FROM records "
        "WHERE user_id = ? AND substr(date, 1, 7) = ? "
        "AND deleted_at IS NULL",
        (user_id, cur_month),
    ).fetchone()["s"]

    # 本月预算总额（如果有）
    budget_total = db.execute(
        "SELECT COALESCE(SUM(amount), 0) AS s FROM budgets "
        "WHERE user_id = ? AND month = ?",
        (user_id, cur_month),
    ).fetchone()["s"]

    # 近 30 天净流入（收入 - 支出）
    d30 = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    income_30 = db.execute(
        "SELECT COALESCE(SUM(amount), 0) AS s FROM income "
        "WHERE user_id = ? AND date >= ? "
        "AND deleted_at IS NULL",
        (user_id, d30),
    ).fetchone()["s"]
    spend_30 = db.execute(
        "SELECT COALESCE(SUM(amount), 0) AS s FROM records "
        "WHERE user_id = ? AND date >= ? "
        "AND deleted_at IS NULL",
        (user_id, d30),
    ).fetchone()["s"]

    # 进行中的储蓄目标
    goals = db.execute(
        "SELECT name, target_amount, current_progress, deadline "
        "FROM financial_goals WHERE user_id = ? AND current_progress < target_amount "
        "AND deleted_at IS NULL "
        "ORDER BY priority ASC LIMIT 3",
        (user_id,),
    ).fetchall()
    goals_list = [{
        "name": g_["name"],
        "target": round(g_["target_amount"], 2),
        "saved": round(g_["current_progress"] or 0, 2),
        "deadline": g_["deadline"],
    } for g_ in goals]

    return {
        "month": cur_month,
        "spend_by_category_3m": by_cat,
        "spend_total_3m": round(total_3m, 2),
        "spend_avg_monthly": round(total_3m / 3, 2),
        "month_spend": round(month_spend, 2),
        "budget_total": round(budget_total, 2),
        "budget_left": round(budget_total - month_spend, 2) if budget_total > 0 else None,
        "income_30d": round(income_30, 2),
        "spend_30d": round(spend_30, 2),
        "net_30d": round(income_30 - spend_30, 2),
        "goals": goals_list,
    }


_RUBRIC_FALLBACK = [
    "🤔 暂时没有调通 AI，先按基本原则衡量：",
    "1) 是冲动消费还是真实需求？睡一觉再决定",
    "2) 价格能不能砍 / 等大促",
    "3) 占月可支配收入的比例（>20% 谨慎）",
    "4) 同价位是否有更便宜替代品",
]


@decide_bp.route("/api/decide", methods=["POST"])
@login_required
def decide():
    """POST {item, price, category?, note?}  → {verdict, reason, alternatives[], impact{}}"""
    payload = request.get_json(silent=True) or {}
    item = str(payload.get("item") or "").strip()[:80]
    note = str(payload.get("note") or "").strip()[:200]
    category = str(payload.get("category") or "").strip()[:30]
    try:
        price = float(payload.get("price") or 0)
    except (TypeError, ValueError):
        price = 0.0

    if not item or price <= 0:
        return jsonify({"error": "请填写物品名称和价格（>0）"}), 400
    if price > 1_000_000:
        return jsonify({"error": "金额过大，请检查输入"}), 400

    # 前端可显式传 llm 配置；无用户自有 key 时 current_llm 会把 url/model 归到
    # constants.py 系统默认(见 services.llm_config.current_llm)。
    llm_cfg = current_llm(payload)

    ctx = _gather_context(g.user_id)

    # 客观影响估算（不依赖 LLM，先算好作为答复 base）
    impact = {
        "price": round(price, 2),
        "as_pct_of_avg_monthly_spend": (
            round(price / ctx["spend_avg_monthly"] * 100, 1)
            if ctx["spend_avg_monthly"] > 0 else None
        ),
        "as_pct_of_net_30d": (
            round(price / ctx["net_30d"] * 100, 1)
            if ctx["net_30d"] > 0 else None
        ),
        "budget_left_after": (
            round(ctx["budget_left"] - price, 2)
            if ctx["budget_left"] is not None else None
        ),
    }

    # 若两边都没 key（用户自定义 + 系统默认），回退到基于规则的本地建议，
    # 避免一次必失败的 HTTP 调用。
    import os as _os
    has_any_key = bool(llm_cfg.get("apikey")) or bool(_os.getenv("DEEPSEEK_API_KEY"))
    if not has_any_key:
        return jsonify({
            "verdict": "建议谨慎",
            "reason": "\n".join(_RUBRIC_FALLBACK),
            "alternatives": [],
            "impact": impact,
            "context_used": ctx,
            "source": "fallback",
        })

    # 拼 prompt — 关键：让 LLM 严格按 JSON 返回，前端好渲染
    system_prompt = (
        "你是「智能记账助手 Anon」的购前决策模块。用户告诉你想买什么、价格多少，"
        "你结合用户**真实**财务数据给出建议。\n"
        "严格按 JSON 返回，键名固定：\n"
        '{ "verdict": "建议买|建议等等|建议买更便宜的|建议放弃", '
        '"reason": "（一段话 ≤120 字，说明判断依据）", '
        '"alternatives": ["（同需求的更便宜替代品 1）", "..."], '
        '"tips": ["（实用购买技巧 1）", "..."] }\n'
        "不要输出 markdown 围栏，不要任何额外文字。\n"
        "判断逻辑参考：占月均支出 > 50% 谨慎；当月预算余量不够 → 建议等等；"
        "进行中的储蓄目标会被延迟 → 提示影响；价格虚高时给替代品。"
    )

    user_prompt = (
        f"我想买：{item}\n"
        f"价格：¥{price:.2f}\n"
        + (f"分类：{category}\n" if category else "")
        + (f"补充说明：{note}\n" if note else "")
        + "\n我的财务现状：\n"
        + f"- 近 3 月月均总支出 ¥{ctx['spend_avg_monthly']:.0f}\n"
        + f"- 本月已花 ¥{ctx['month_spend']:.0f}"
        + (f"，本月预算总额 ¥{ctx['budget_total']:.0f}，剩 ¥{ctx['budget_left']:.0f}\n"
           if ctx["budget_left"] is not None else "\n")
        + f"- 近 30 天净流入 ¥{ctx['net_30d']:.0f}（收 ¥{ctx['income_30d']:.0f} / 支 ¥{ctx['spend_30d']:.0f}）\n"
        + (f"- 近 3 月支出 Top: " +
           "、".join(f"{x['category']}¥{x['total']:.0f}" for x in ctx["spend_by_category_3m"][:5])
           + "\n" if ctx["spend_by_category_3m"] else "")
        + (f"- 在攒：" + "、".join(
            f"{g_['name']}(已存{g_['saved']:.0f}/{g_['target']:.0f})"
            for g_ in ctx["goals"]) + "\n" if ctx["goals"] else "")
    )

    llm_error_msg: str | None = None
    try:
        result = _call_llm(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            llm=llm_cfg,
            temperature=0.4,
            timeout=LLM_TIMEOUT_LONG,
            endpoint="decide.advise",
        )
        if not result:
            raise RuntimeError("LLM 无响应")
        if "error" in result:
            err = result["error"]
            llm_error_msg = err.get("message") if isinstance(err, dict) else str(err)
            raise RuntimeError(llm_error_msg or "LLM 返回错误")
        if "choices" not in result:
            raise RuntimeError("LLM 响应缺少 choices")
        raw = (result["choices"][0]["message"].get("content") or "").strip()
        # 兼容 LLM 偶尔仍带 ``` 围栏
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()
        parsed = json.loads(raw)
        verdict = str(parsed.get("verdict") or "建议谨慎")[:20]
        reason = str(parsed.get("reason") or "")[:500]
        alts = [str(x)[:80] for x in (parsed.get("alternatives") or [])][:5]
        tips = [str(x)[:80] for x in (parsed.get("tips") or [])][:5]
        return jsonify({
            "verdict": verdict, "reason": reason,
            "alternatives": alts, "tips": tips,
            "impact": impact, "context_used": ctx, "source": "llm",
        })
    except Exception as e:  # noqa: BLE001
        logger.warning("decide LLM 失败，回退本地建议: %s", e)
        # LLM 调通了但失败（超时 / 配额 / 解析失败） vs 完全没调通：文案区分
        if llm_error_msg:
            fallback_reason = (
                f"⚠️ AI 调用失败：{llm_error_msg[:80]}\n"
                "下面是按通用原则给出的建议——\n"
                + "\n".join(_RUBRIC_FALLBACK[1:])
            )
        else:
            fallback_reason = "\n".join(_RUBRIC_FALLBACK)
        return jsonify({
            "verdict": "建议谨慎",
            "reason": fallback_reason,
            "alternatives": [], "tips": [],
            "impact": impact, "context_used": ctx, "source": "fallback",
        })
