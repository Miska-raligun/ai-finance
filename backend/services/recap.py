"""本月回顾：聚合月度亮点 + LLM 俏皮文案，供动森风「本月回顾卡片」使用。

数字底座复用 services.reports._aggregate（与月度报告口径一致，避免同月两处对不上）；
仅额外算几个「亮点」指标（花最多的一天 / 最大单笔 / 连续记账 / 环比）。
文案走 _call_llm，无 key / 解析失败时本地模板兜底。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from db import get_db
from services.llm import _call_llm
from services.reports import _aggregate

logger = logging.getLogger(__name__)


def _prev_period(period: str) -> str:
    y, m = int(period[:4]), int(period[5:7])
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def _longest_streak(dates: list[str]) -> int:
    """给定日期字符串列表（YYYY-MM-DD），返回最长连续天数。"""
    if not dates:
        return 0
    ds = sorted({datetime.strptime(d, "%Y-%m-%d").date() for d in dates})
    best = run = 1
    for i in range(1, len(ds)):
        if (ds[i] - ds[i - 1]).days == 1:
            run += 1
            best = max(best, run)
        else:
            run = 1
    return best


def compute_recap(user_id: int, period: str, llm: dict | None = None) -> dict:
    """返回本月回顾亮点 + 文案。period 形如 YYYY-MM。"""
    db = get_db()
    agg = _aggregate(user_id, period)

    hi = db.execute(
        "SELECT date, SUM(amount) AS total FROM records "
        "WHERE user_id = ? AND strftime('%Y-%m', date) = ? "
        "AND deleted_at IS NULL "
        "GROUP BY date ORDER BY total DESC LIMIT 1",
        (user_id, period),
    ).fetchone()
    highest_day = {"date": hi["date"], "total": round(hi["total"], 2)} if hi else None

    lg = db.execute(
        "SELECT date, category, amount, note FROM records "
        "WHERE user_id = ? AND strftime('%Y-%m', date) = ? "
        "AND deleted_at IS NULL "
        "ORDER BY amount DESC LIMIT 1",
        (user_id, period),
    ).fetchone()
    largest_txn = dict(lg) if lg else None
    if largest_txn:
        largest_txn["amount"] = round(largest_txn["amount"], 2)

    day_rows = db.execute(
        "SELECT date FROM records "
        "WHERE user_id = ? AND strftime('%Y-%m', date) = ? AND deleted_at IS NULL "
        "UNION SELECT date FROM income "
        "WHERE user_id = ? AND strftime('%Y-%m', date) = ? AND deleted_at IS NULL",
        (user_id, period, user_id, period),
    ).fetchall()
    days = [r["date"] for r in day_rows]
    active_days = len(set(days))
    streak = _longest_streak(days)

    record_count = sum(int(r["cnt"]) for r in agg["by_category_spend"])
    top_category = agg["by_category_spend"][0] if agg["by_category_spend"] else None

    prev = _prev_period(period)
    prev_spend = db.execute(
        "SELECT COALESCE(SUM(amount), 0) AS s FROM records "
        "WHERE user_id = ? AND strftime('%Y-%m', date) = ? "
        "AND deleted_at IS NULL",
        (user_id, prev),
    ).fetchone()["s"]
    cur_spend = agg["spend_total"]
    mom_pct = (round((cur_spend - prev_spend) / prev_spend * 100, 1)
               if prev_spend > 0 else None)

    highlights = {
        "period": period,
        "spend_total": agg["spend_total"],
        "income_total": agg["income_total"],
        "net": agg["net"],
        "record_count": record_count,
        "active_days": active_days,
        "streak": streak,
        "top_category": top_category,
        "highest_day": highest_day,
        "largest_txn": largest_txn,
        "mom": {"prev_spend": round(prev_spend, 2), "change_pct": mom_pct},
    }

    has_data = bool(agg["by_category_spend"] or agg["by_category_income"])
    if not has_data:
        highlights["caption"] = "这个月还没有记账数据哦，记几笔再回来看看吧～ 🐾"
        highlights["source"] = "empty"
    else:
        caption, source = _make_caption(highlights, llm)
        highlights["caption"] = caption
        highlights["source"] = source
    return highlights


def _make_caption(h: dict, llm: dict | None) -> tuple[str, str]:
    import os
    llm = llm or {}
    has_key = bool(llm.get("apikey")) or bool(os.getenv("DEEPSEEK_API_KEY"))
    if not has_key:
        return _template_caption(h), "fallback"

    system = (
        "你是「智能记账助手 Anon」的本月回顾文案模块，语气俏皮亲切，像动森里的小动物管家。"
        "根据用户本月数据写 1-2 句中文回顾文案，不超过 60 字，可带 1-2 个 emoji，"
        "不要罗列数字清单，不要 markdown，直接输出文案本身。"
    )
    user = "本月数据：\n```json\n" + json.dumps(h, ensure_ascii=False) + "\n```"
    try:
        result = _call_llm(
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            llm=llm, temperature=0.8, timeout=20, endpoint="recap.caption",
        )
        if not result or "error" in result or "choices" not in result:
            raise RuntimeError("llm unavailable")
        text = (result["choices"][0]["message"].get("content") or "").strip()
        text = text.strip("`").strip()
        if not text:
            raise RuntimeError("empty caption")
        return text[:120], "llm"
    except Exception as e:  # noqa: BLE001
        logger.warning("recap caption 回退本地: %s", e)
        return _template_caption(h), "fallback"


def _template_caption(h: dict) -> str:
    parts = []
    tc = h.get("top_category")
    if tc:
        parts.append(f"这个月你最舍得在「{tc['category']}」上花钱")
    hd = h.get("highest_day")
    if hd and hd.get("date"):
        parts.append(f"{hd['date'][5:]} 是你的剁手日")
    if h.get("streak", 0) >= 3:
        parts.append(f"连续记账 {h['streak']} 天，坚持得不错")
    if not parts:
        parts.append("这个月的账本已经记好啦")
    return "，".join(parts) + " 🐾"
