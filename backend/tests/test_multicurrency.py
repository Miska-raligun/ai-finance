"""多币种:组合汇总把 USD/HKD 资产折算成 CNY 再相加,不再裸加。"""
from __future__ import annotations

import pytest

import services.portfolio as pf
from services.portfolio import compute_allocation, compute_return, build_holding_details


@pytest.fixture(autouse=True)
def fixed_fx(monkeypatch):
    """固定汇率,避免测试联网:USD=7.0, HKD=0.9, CNY=1.0。"""
    rates = {"USD": 7.0, "HKD": 0.9, "CNY": 1.0}
    monkeypatch.setattr(pf, "_fx_resolver", lambda cur: rates.get((cur or "CNY").upper(), 1.0))


def test_allocation_converts_to_cny():
    assets = [
        {"id": 1, "name": "茅台", "type": "股票", "current_value": 1000, "currency": "CNY"},
        {"id": 2, "name": "AAPL", "type": "美股", "current_value": 100, "currency": "USD"},  # =700 CNY
    ]
    alloc = compute_allocation(assets)
    # 总市值 = 1000 + 700 = 1700,而不是裸加的 1100
    assert alloc["total_value"] == 1700.0
    aapl = next(a for a in alloc["by_asset"] if a["name"] == "AAPL")
    assert aapl["value"] == 700.0
    assert aapl["pct"] == pytest.approx(700 / 1700 * 100, abs=0.1)


def test_return_converts_both_value_and_cost():
    assets = [
        {"current_value": 120, "cost_basis": 100, "currency": "USD"},  # 840 / 700 CNY
        {"current_value": 500, "cost_basis": 400, "currency": "CNY"},
    ]
    r = compute_return(assets)
    assert r["total_value"] == pytest.approx(120 * 7 + 500)   # 1340
    assert r["total_cost"] == pytest.approx(100 * 7 + 400)    # 1100
    assert r["pnl"] == pytest.approx(240)


def test_holding_weight_is_cny_normalized_but_pnl_native():
    assets = [
        {"name": "AAPL", "current_value": 100, "cost_basis": 80, "currency": "USD"},
        {"name": "茅台", "current_value": 300, "cost_basis": 300, "currency": "CNY"},
    ]
    details = build_holding_details(assets)
    aapl = next(d for d in details if d["name"] == "AAPL")
    # 盈亏率是原币比值,与币种无关:(100-80)/80 = 25%
    assert aapl["pnl_pct"] == pytest.approx(25.0)
    # 权重按 CNY:700 / (700+300) = 70%
    assert aapl["weight_pct"] == pytest.approx(70.0, abs=0.1)
    assert aapl["currency"] == "USD"


def test_cny_only_unchanged():
    """纯 CNY 组合结果和折算前一致(向后兼容)。"""
    assets = [{"current_value": 100, "cost_basis": 50, "currency": "CNY"}]
    r = compute_return(assets)
    assert r["total_value"] == 100 and r["total_cost"] == 50 and r["pnl"] == 50
