"""services.portfolio 纯函数测试。"""
from services.portfolio import (
    compute_allocation, compute_drift, compute_goal_plan, compute_return,
)


def test_allocation_sums_to_total():
    assets = [
        {"name": "A", "type": "stock", "current_value": 300, "cost_basis": 250},
        {"name": "B", "type": "fund", "current_value": 500, "cost_basis": 500},
        {"name": "C", "type": "cash", "current_value": 200, "cost_basis": 200},
    ]
    allo = compute_allocation(assets)
    assert allo["total_value"] == 1000.0
    pct_sum = sum(r["pct"] for r in allo["by_type"])
    assert abs(pct_sum - 100.0) < 0.1


def test_allocation_empty():
    allo = compute_allocation([])
    assert allo["total_value"] == 0
    assert allo["by_type"] == []
    assert allo["by_asset"] == []


def test_return_pct():
    assets = [
        {"current_value": 110, "cost_basis": 100},
        {"current_value": 90, "cost_basis": 100},
    ]
    ret = compute_return(assets)
    assert ret["total_value"] == 200
    assert ret["total_cost"] == 200
    assert ret["pnl"] == 0
    assert ret["return_pct"] == 0


def test_drift_respects_risk_level():
    # aggressive target: stock=45%, bond=10% → 一个持仓全是债券的人应被建议减债增股
    allo = {"by_type": [
        {"type": "bond", "pct": 90},
        {"type": "stock", "pct": 10},
    ]}
    drift = compute_drift(allo, risk_level="aggressive")
    bond_row = next(d for d in drift if d["type"] == "bond")
    stock_row = next(d for d in drift if d["type"] == "stock")
    assert bond_row["drift_pct"] > 0
    assert bond_row["action"] == "建议减仓"
    assert stock_row["action"] == "建议加仓"


def test_goal_plan_three_levels():
    plan = compute_goal_plan(
        target_amount=100000, current_progress=20000,
        deadline="2030-04-17", monthly_net_cashflow=2000,
    )
    assert plan["gap"] == 80000.0
    assert plan["months_left"] > 0
    assert len(plan["plans"]) == 3
    levels = {p["level"] for p in plan["plans"]}
    assert levels == {"conservative", "balanced", "aggressive"}
    # 激进档月供应比保守档小（同样目标同样期限，利率高则月供低）
    pmt = {p["level"]: p["monthly_pmt"] for p in plan["plans"]}
    assert pmt["aggressive"] < pmt["conservative"]
