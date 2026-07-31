"""年度预算:period=YYYY 存年度预算,已花按整年汇总,与月度并存。"""
from __future__ import annotations


def _add_expense(client, category, amount, date):
    client.post("/api/records", json={"category": category, "amount": amount, "note": "", "date": date})


def test_annual_budget_sums_whole_year(app, auth_client):
    _add_expense(auth_client, "旅行", 3000, "2026-03-10")
    _add_expense(auth_client, "旅行", 2000, "2026-08-20")
    r = auth_client.post("/api/budgets", json={"category": "旅行", "amount": 10000, "period": "2026"})
    assert r.status_code == 200

    got = auth_client.get("/api/budgets", query_string={"period": "2026"}).get_json()
    row = next(b for b in got if b["category"] == "旅行")
    assert row["cycle"] == "yearly"
    assert row["amount"] == 10000
    assert row["remaining"] == 5000   # 10000 - (3000+2000)


def test_monthly_and_annual_coexist(app, auth_client):
    _add_expense(auth_client, "餐饮", 800, "2026-07-15")
    auth_client.post("/api/budgets", json={"category": "餐饮", "amount": 1000, "period": "2026-07"})
    auth_client.post("/api/budgets", json={"category": "餐饮", "amount": 12000, "period": "2026"})

    monthly = auth_client.get("/api/budgets", query_string={"period": "2026-07"}).get_json()
    yearly = auth_client.get("/api/budgets", query_string={"period": "2026"}).get_json()

    m = next(b for b in monthly if b["category"] == "餐饮")
    y = next(b for b in yearly if b["category"] == "餐饮")
    assert m["cycle"] == "monthly" and m["remaining"] == 200      # 1000-800
    assert y["cycle"] == "yearly" and y["remaining"] == 11200     # 12000-800


def test_legacy_month_param_still_works(app, auth_client):
    _add_expense(auth_client, "交通", 100, "2026-07-01")
    auth_client.post("/api/budgets", json={"category": "交通", "amount": 500, "month": "2026-07"})
    got = auth_client.get("/api/budgets", query_string={"month": "2026-07"}).get_json()
    row = next(b for b in got if b["category"] == "交通")
    assert row["remaining"] == 400 and row["cycle"] == "monthly"


def test_all_budgets_branch_handles_both(app, auth_client):
    _add_expense(auth_client, "旅行", 3000, "2026-03-10")
    auth_client.post("/api/budgets", json={"category": "旅行", "amount": 10000, "period": "2026"})
    allb = auth_client.get("/api/budgets").get_json()   # 无 period → 全部
    yearly = next(b for b in allb if b["category"] == "旅行" and b["cycle"] == "yearly")
    assert yearly["remaining"] == 7000
