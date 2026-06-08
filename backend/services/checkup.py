"""财务体检：聚合财务画像 → LLM 直接打分(0-100) + 四维拆解 + 报告 → 存档。

按产品要求不写死评分公式，分数由 LLM 基于**真实**数据给出；无 key / 解析失败时
退回本地规则估算（带 source 标记）。结果 upsert 到 checkup_scores，供历史趋势线复用。
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from db import get_db
from services.llm import _call_llm
from services.reports import _aggregate

logger = logging.getLogger(__name__)

_GRADES = [(80, "健康"), (60, "良好"), (40, "亚健康"), (0, "需调理")]


def grade_of(score: int) -> str:
    for lo, name in _GRADES:
        if score >= lo:
            return name
    return "需调理"


def _recent_months(period: str, n: int) -> list[str]:
    y, m = int(period[:4]), int(period[5:7])
    out = []
    for _ in range(n):
        out.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return out


def _month_value_change(db, user_id: int, period: str) -> float:
    """当月市值变动估算：月末持仓总市值 − 月前持仓总市值（按 asset_value_history 最新快照）。

    月内新建/清仓也会反映进来，作为「投资情况」打分的粗粒度信号，足够 LLM/规则定向。
    """
    prev = _recent_months(period, 2)[1]

    def total_at_or_before(p: str) -> float:
        # 每个 asset 取「<=p 月份」的最新一条快照——用 window function (ROW_NUMBER OVER
        # PARTITION BY asset_id ORDER BY recorded_at DESC) 直接命中现有的
        # idx_asset_value_history_asset_time(asset_id, recorded_at DESC) 索引，
        # 避免旧实现的相关子查询 `id = (SELECT MAX(id) ...)` 在 history 表膨胀后每行
        # 都嵌套循环。
        # JOIN assets 过滤掉已软删的资产，避免遗留 history 行膨胀月差。
        row = db.execute(
            """
            SELECT COALESCE(SUM(h.value), 0) AS s
            FROM (
                SELECT asset_id, value,
                       ROW_NUMBER() OVER (
                           PARTITION BY asset_id ORDER BY recorded_at DESC
                       ) AS rn
                FROM asset_value_history
                WHERE user_id = ? AND substr(recorded_at, 1, 7) <= ?
            ) h
            JOIN assets a ON a.id = h.asset_id
            WHERE h.rn = 1 AND a.deleted_at IS NULL
            """,
            (user_id, p),
        ).fetchone()
        return float(row["s"] or 0)

    return round(total_at_or_before(period) - total_at_or_before(prev), 2)


def _gather(user_id: int, period: str) -> dict:
    """采集体检所需画像：储蓄率 / 预算执行 / 投资情况 / 消费结构。"""
    db = get_db()
    agg = _aggregate(user_id, period)

    months = _recent_months(period, 3)
    placeholders = ",".join("?" * len(months))
    spend_3m = db.execute(
        f"SELECT COALESCE(SUM(amount), 0) AS s FROM records "
        f"WHERE user_id = ? AND strftime('%Y-%m', date) IN ({placeholders}) "
        f"AND deleted_at IS NULL",
        (user_id, *months),
    ).fetchone()["s"]
    avg_monthly_spend = round(spend_3m / 3, 2)

    spend_map = {s["category"]: s["total"] for s in agg["by_category_spend"]}
    budget_overrun = []
    for b in agg["budgets"]:
        spent = spend_map.get(b["category"], 0)
        if spent > b["amount"]:
            budget_overrun.append({
                "category": b["category"],
                "budget": round(b["amount"], 2),
                "spent": round(spent, 2),
            })

    income = agg["income_total"]
    savings_rate = round(agg["net"] / income * 100, 1) if income > 0 else None
    top_cat_share = (
        round(agg["by_category_spend"][0]["total"] / agg["spend_total"] * 100, 1)
        if agg["spend_total"] > 0 and agg["by_category_spend"] else None
    )

    # 投资情况：在 _aggregate_portfolio 给出的累计快照（pnl / return_pct）上叠加当月市值变动
    portfolio = dict(agg.get("portfolio") or {})
    portfolio["month_value_change"] = _month_value_change(db, user_id, period)
    if portfolio.get("has_portfolio") and (portfolio.get("total_value") or 0) > 0:
        portfolio["month_change_pct"] = round(
            portfolio["month_value_change"] / portfolio["total_value"] * 100, 2
        )
    else:
        portfolio["month_change_pct"] = None

    return {
        "period": period,
        "income_total": agg["income_total"],
        "spend_total": agg["spend_total"],
        "net": agg["net"],
        "savings_rate_pct": savings_rate,
        "avg_monthly_spend_3m": avg_monthly_spend,
        "budget_total": round(sum(b["amount"] for b in agg["budgets"]), 2),
        "budget_set": bool(agg["budgets"]),
        "budget_overrun": budget_overrun,
        "top_category": agg["by_category_spend"][0] if agg["by_category_spend"] else None,
        "top_category_share_pct": top_cat_share,
        "by_category_spend": agg["by_category_spend"][:8],
        "portfolio": portfolio,
    }


def compute_checkup(user_id: int, period: str, llm: dict | None = None) -> dict:
    ctx = _gather(user_id, period)
    has_data = bool(ctx["spend_total"] or ctx["income_total"])
    llm = llm or {}
    has_key = bool(llm.get("apikey")) or bool(os.getenv("DEEPSEEK_API_KEY"))

    if not has_data:
        result = {
            "score": 0, "dimensions": [],
            "summary": "本月暂无收支数据，记几笔后再来体检吧。",
            "report": "", "source": "empty",
        }
    elif not has_key:
        result = _fallback(ctx)
    else:
        result = _llm_score(ctx, llm) or _fallback(ctx)

    result["period"] = period
    result["grade"] = grade_of(int(result.get("score") or 0))
    result["context"] = ctx
    if result["source"] != "empty":
        _save(user_id, period, result)
    return result


def _llm_score(ctx: dict, llm: dict) -> dict | None:
    system = (
        "你是「智能记账助手 Anon」的财务体检模块。基于用户**真实**财务数据，给出 0-100 的"
        "财务健康总分，并从四个维度评分：储蓄率、预算执行、投资情况、消费结构。\n"
        "严格按 JSON 返回，不要 markdown 围栏，不要任何额外文字：\n"
        '{ "score": 0到100的整数, '
        '"dimensions": [ {"name":"储蓄率","score":0到25,"max":25,"comment":"≤40字点评"}, '
        '{"name":"预算执行","score":0到25,"max":25,"comment":"..."}, '
        '{"name":"投资情况","score":0到25,"max":25,"comment":"..."}, '
        '{"name":"消费结构","score":0到25,"max":25,"comment":"..."} ], '
        '"summary":"一句话总评 ≤40字", '
        '"report":"分维度诊断 + 改进建议，纯文本，可换行分段，≤300字" }\n'
        "评分参考：储蓄率越高越好(≥30%给满分)；当月有预算且不超支得分高，未设预算给中性偏低分并提示设预算；"
        "投资情况看 portfolio：优先用 month_change_pct（当月市值变动比例）评估本月表现，"
        "若无则用 return_pct（累计收益率）兜底——当月或累计为正给高分、深度回撤给低分、"
        "未建仓给中性偏低并建议小额起步；单一分类占比越低越均衡。"
        "总分应约等于四个维度之和。禁止编造未提供的数字。"
    )
    user = "我的财务数据：\n```json\n" + json.dumps(ctx, ensure_ascii=False) + "\n```"
    try:
        result = _call_llm(
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            llm=llm, temperature=0.3, timeout=30, endpoint="checkup.score",
        )
        if not result or "error" in result or "choices" not in result:
            return None
        raw = (result["choices"][0]["message"].get("content") or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()
        parsed = json.loads(raw)
        score = int(max(0, min(100, int(parsed.get("score") or 0))))
        dims = []
        for d in (parsed.get("dimensions") or [])[:4]:
            dims.append({
                "name": str(d.get("name") or "")[:10],
                "score": round(float(d.get("score") or 0), 1),
                "max": round(float(d.get("max") or 25), 1),
                "comment": str(d.get("comment") or "")[:120],
            })
        return {
            "score": score,
            "dimensions": dims,
            "summary": str(parsed.get("summary") or "")[:120],
            "report": str(parsed.get("report") or "")[:1000],
            "source": "llm",
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("checkup LLM 失败，回退本地: %s", e)
        return None


def _fallback(ctx: dict) -> dict:
    def clamp(v, lo, hi):
        return max(lo, min(hi, v))

    sr = ctx["savings_rate_pct"]
    sr_score = round(clamp((sr or 0) / 30, 0, 1) * 25, 1)

    if not ctx["budget_set"]:
        bud_score = 12.0
        bud_comment = "尚未设置预算，建议先给主要分类设月预算。"
    else:
        cats = ctx.get("by_category_spend") or []
        n_over = len(ctx["budget_overrun"])
        bud_score = round(clamp(1 - n_over / max(1, len(cats)), 0, 1) * 25, 1)
        bud_comment = "预算执行良好。" if n_over == 0 else f"{n_over} 个分类超支，注意收敛。"

    inv = ctx.get("portfolio") or {}
    if not inv.get("has_portfolio"):
        inv_score = 10.0
        inv_comment = "尚未录入投资资产，建议开个小仓位先动起来。"
    else:
        mc_pct = inv.get("month_change_pct")
        if mc_pct is not None:
            # 当月市值变动率（首选信号）
            if mc_pct >= 5: inv_score = 25.0
            elif mc_pct >= 2: inv_score = 22.0
            elif mc_pct >= 0: inv_score = 18.0
            elif mc_pct >= -2: inv_score = 14.0
            elif mc_pct >= -5: inv_score = 9.0
            else: inv_score = 4.0
            mvc = inv.get("month_value_change") or 0
            inv_comment = f"本月市值变动 {mc_pct:+.1f}%（¥{mvc:+,.0f}）。"
        else:
            # 累计收益率兜底
            rpct = float(inv.get("return_pct") or 0)
            if rpct >= 10: inv_score = 25.0
            elif rpct >= 5: inv_score = 22.0
            elif rpct >= 0: inv_score = 18.0
            elif rpct >= -5: inv_score = 12.0
            elif rpct >= -10: inv_score = 7.0
            else: inv_score = 3.0
            inv_comment = f"累计收益率 {rpct}%（暂无当月快照）。"

    share = ctx["top_category_share_pct"]
    struct_score = round(clamp(1 - max(0, (share or 0) - 40) / 60, 0, 1) * 25, 1)

    dims = [
        {"name": "储蓄率", "score": sr_score, "max": 25,
         "comment": (f"储蓄率 {sr}%。" if sr is not None else "本月无收入，难评估储蓄率。")},
        {"name": "预算执行", "score": bud_score, "max": 25, "comment": bud_comment},
        {"name": "投资情况", "score": inv_score, "max": 25, "comment": inv_comment},
        {"name": "消费结构", "score": struct_score, "max": 25,
         "comment": (f"最大分类占比 {share}%。" if share is not None else "本月暂无支出。")},
    ]
    total = int(round(sum(d["score"] for d in dims)))
    return {
        "score": total,
        "dimensions": dims,
        "summary": "（本地规则估算，配置 AI 后可获得更精准的体检）",
        "report": "未调用 AI，按基础规则给出分数：\n"
                  + "\n".join(f"· {d['name']}：{d['comment']}" for d in dims),
        "source": "fallback",
    }


def _save(user_id: int, period: str, result: dict) -> None:
    get_db().execute(
        """
        INSERT INTO checkup_scores
            (user_id, period, score, dimensions_json, report, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, period) DO UPDATE SET
            score = excluded.score,
            dimensions_json = excluded.dimensions_json,
            report = excluded.report,
            source = excluded.source,
            created_at = excluded.created_at
        """,
        (user_id, period, int(result.get("score") or 0),
         json.dumps(result.get("dimensions") or [], ensure_ascii=False),
         result.get("report") or "", result.get("source") or "llm",
         datetime.now().isoformat(timespec="seconds")),
    )
    get_db().commit()


def get_checkup_history(user_id: int, months: int = 12) -> list[dict]:
    rows = get_db().execute(
        "SELECT period, score FROM checkup_scores WHERE user_id = ? "
        "ORDER BY period DESC LIMIT ?",
        (user_id, months),
    ).fetchall()
    return list(reversed([dict(r) for r in rows]))


def get_checkup(user_id: int, period: str) -> dict | None:
    row = get_db().execute(
        "SELECT period, score, dimensions_json, report, source, created_at "
        "FROM checkup_scores WHERE user_id = ? AND period = ?",
        (user_id, period),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["dimensions"] = json.loads(d.pop("dimensions_json") or "[]")
    except json.JSONDecodeError:
        d.pop("dimensions_json", None)
        d["dimensions"] = []
    d["grade"] = grade_of(int(d.get("score") or 0))
    return d
