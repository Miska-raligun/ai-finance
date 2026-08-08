"""投资组合纯函数计算：分配、漂移、回报率，全部不依赖外部 API。

目标占比（RISK_TARGET_ALLOCATION / DEFAULT_TARGET_ALLOCATION）已移除；
再平衡的目标配比现在由 services.rebalance.suggest_targets 交给 LLM 现场推荐。
compute_drift 保留，但必须显式传入 target（字典 {type → 0~1 比例}）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable


# 汇率解析器:把某币种折算成 CNY 的倍率。默认调 services.quotes.get_fx_to_cny
# (带缓存 + 兜底),测试可替换成固定汇率。抽成模块级 hook 是为了让下面的
# compute_* 汇总函数保持"接收 asset dict 即可"的调用签名不变。
def _default_fx(currency: str | None) -> float:
    try:
        from services.quotes import get_fx_to_cny
        return get_fx_to_cny(currency)
    except Exception:  # noqa: BLE001 — 汇率不可用不应阻断组合计算
        return 1.0


_fx_resolver = _default_fx


def _cny(value, currency: str | None) -> float:
    """把原币金额折算成 CNY。"""
    return float(value or 0) * _fx_resolver(currency)


def _asset_cny(a: dict) -> float:
    return _cny(a.get("current_value"), a.get("currency"))


def _cost_cny(a: dict) -> float:
    return _cny(a.get("cost_basis"), a.get("currency"))


def _ensure_dict(rows: Iterable) -> list[dict]:
    """sqlite3.Row 可能传进来，统一转成 dict 方便操作。"""
    out = []
    for r in rows:
        if isinstance(r, dict):
            out.append(r)
        else:
            out.append({k: r[k] for k in r.keys()})
    return out


def compute_allocation(assets: Iterable) -> dict:
    """根据持仓 current_value 计算总市值与各类型占比。

    返回：{total_value, by_type:[{type,value,pct}], by_asset:[{name,type,value,pct}]}
    """
    items = _ensure_dict(assets)
    # 全部折算成 CNY 再算占比,否则美股(USD)/港股(HKD)数值裸加会让总市值和
    # 占比失真。单笔展示的原币金额由前端另行处理,这里的 value 统一是 CNY。
    total = float(sum(_asset_cny(a) for a in items))

    by_type_map: dict[str, float] = {}
    for a in items:
        t = (a.get("type") or "other").strip() or "other"
        by_type_map[t] = by_type_map.get(t, 0.0) + _asset_cny(a)

    by_type = []
    for t, v in sorted(by_type_map.items(), key=lambda x: x[1], reverse=True):
        by_type.append({
            "type": t,
            "value": round(v, 2),
            "pct": round((v / total * 100) if total > 0 else 0.0, 2),
        })

    by_asset = []
    for a in items:
        v = _asset_cny(a)
        by_asset.append({
            "id": a.get("id"),
            "name": a.get("name"),
            "type": a.get("type"),
            "value": round(v, 2),
            "pct": round((v / total * 100) if total > 0 else 0.0, 2),
        })
    by_asset.sort(key=lambda x: x["value"], reverse=True)

    return {
        "total_value": round(total, 2),
        "by_type": by_type,
        "by_asset": by_asset,
    }


def compute_drift(allocation: dict, target: dict) -> list[dict]:
    """基于当前 allocation 与目标占比，计算各类型漂移百分比。

    target 必须由调用方提供（字典 {type → 0~1 比例}）；由
    services.rebalance.suggest_targets 或用户自定义生成。
    返回：[{type, current_pct, target_pct, drift_pct, action}]
    """
    target = target or {}
    cur = {row["type"]: row["pct"] for row in allocation.get("by_type", [])}
    types = set(cur) | set(target.keys())

    out = []
    for t in sorted(types):
        cur_pct = cur.get(t, 0.0)
        tgt_pct = target.get(t, 0.0) * 100  # target 用 0~1 表示
        drift = round(cur_pct - tgt_pct, 2)
        if abs(drift) < 1.0:
            action = "保持"
        elif drift > 0:
            action = "建议减仓"
        else:
            action = "建议加仓"
        out.append({
            "type": t,
            "current_pct": round(cur_pct, 2),
            "target_pct": round(tgt_pct, 2),
            "drift_pct": drift,
            "action": action,
        })
    return out


def compute_return(assets: Iterable) -> dict:
    """简化总回报：(current_value 之和 - cost_basis 之和) / cost_basis 之和。
    跨币种资产先各自折算成 CNY 再相加。"""
    items = _ensure_dict(assets)
    total_value = float(sum(_asset_cny(a) for a in items))
    total_cost = float(sum(_cost_cny(a) for a in items))
    pnl = total_value - total_cost
    pct = (pnl / total_cost * 100) if total_cost > 0 else 0.0
    return {
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "pnl": round(pnl, 2),
        "return_pct": round(pct, 2),
    }


def build_holding_details(assets: Iterable) -> list[dict]:
    """给 LLM 用的每笔持仓明细：含 symbol / holdings / 盈亏金额+百分比 / 市值占比。"""
    items = _ensure_dict(assets)
    # 组合权重按 CNY 归一;单笔金额/盈亏保持原币(盈亏率是比值,与币种无关)。
    total_value = float(sum(_asset_cny(a) for a in items)) or 0.0
    out = []
    for a in items:
        cost = float(a.get("cost_basis") or 0)
        value = float(a.get("current_value") or 0)
        pnl_val = value - cost
        pnl_pct = (pnl_val / cost * 100) if cost > 0 else 0.0
        out.append({
            "name": a.get("name"),
            "type": a.get("type"),
            "symbol": a.get("symbol") or "",
            "holdings": a.get("holdings") or 0,
            "currency": a.get("currency") or "CNY",
            "cost_basis": round(cost, 2),
            "current_value": round(value, 2),
            "pnl_value": round(pnl_val, 2),
            "pnl_pct": round(pnl_pct, 2),
            "weight_pct": round((_asset_cny(a) / total_value * 100) if total_value > 0 else 0.0, 2),
        })
    out.sort(key=lambda x: x["current_value"], reverse=True)
    return out


def compute_top_movers(assets: Iterable, top_n: int = 3) -> list[dict]:
    """按单品种盈亏百分比排序，返回涨/跌前 N 名。"""
    items = _ensure_dict(assets)
    movers = []
    for a in items:
        cost = float(a.get("cost_basis") or 0)
        value = float(a.get("current_value") or 0)
        if cost <= 0:
            continue
        pnl_pct = (value - cost) / cost * 100
        movers.append({
            "id": a.get("id"),
            "name": a.get("name"),
            "type": a.get("type"),
            "pnl_pct": round(pnl_pct, 2),
            "pnl_value": round(value - cost, 2),
        })
    movers.sort(key=lambda x: x["pnl_pct"], reverse=True)
    return movers[:top_n] + movers[-top_n:][::-1] if len(movers) > top_n * 2 else movers


def compute_goal_plan(target_amount: float, current_progress: float, deadline: str | None,
                      monthly_net_cashflow: float = 0.0, priority: int | None = None) -> dict:
    """三档储蓄方案（保守 3% / 平衡 6% / 激进 9%）下的月供建议。

    使用未来值年金近似公式：FV = PMT * ((1+r/12)^n - 1) / (r/12)
    priority 1~2 时推荐上浮一档（例：平衡 → 激进），引导用户更激进地完成高优先级目标。
    返回：{months_left, gap, plans:[{level, annual_rate, monthly_pmt, feasible}], recommended_level}
    """
    today = datetime.now().date()
    if deadline:
        try:
            d = datetime.strptime(deadline, "%Y-%m-%d").date()
            months_left = max(1, (d.year - today.year) * 12 + (d.month - today.month))
        except ValueError:
            months_left = 60  # 兜底 5 年
    else:
        months_left = 60

    gap = max(0.0, float(target_amount) - float(current_progress or 0))
    plans = []
    for level, rate in (("conservative", 0.03), ("balanced", 0.06), ("aggressive", 0.09)):
        monthly_rate = rate / 12
        if monthly_rate > 0:
            denom = ((1 + monthly_rate) ** months_left - 1) / monthly_rate
            pmt = gap / denom if denom > 0 else gap / months_left
        else:
            pmt = gap / months_left
        plans.append({
            "level": level,
            "annual_rate": rate,
            "monthly_pmt": round(pmt, 2),
            "feasible": (monthly_net_cashflow == 0) or (pmt <= monthly_net_cashflow),
        })

    # 默认推"平衡"；priority 1~2 上浮到"激进"；priority 5 下沉到"保守"
    recommended = "balanced"
    if priority is not None:
        try:
            p = int(priority)
            if p <= 2:
                recommended = "aggressive"
            elif p >= 5:
                recommended = "conservative"
        except (TypeError, ValueError):
            pass

    return {
        "months_left": months_left,
        "gap": round(gap, 2),
        "monthly_net_cashflow": round(float(monthly_net_cashflow or 0), 2),
        "plans": plans,
        "priority": priority,
        "recommended_level": recommended,
    }
