"""投资模块 REST 路由集成测试。"""


def test_assets_crud_and_portfolio(auth_client):
    # 新建资产
    r1 = auth_client.post("/api/investment/assets", json={
        "name": "沪深300", "type": "fund", "holdings": 1000,
        "cost_basis": 1500, "current_value": 1800,
    })
    assert r1.status_code == 201, r1.data
    asset_id = r1.get_json()["id"]

    r2 = auth_client.post("/api/investment/assets", json={
        "name": "活期存款", "type": "cash", "current_value": 2000,
    })
    assert r2.status_code == 201

    # 列表
    lst = auth_client.get("/api/investment/assets").get_json()
    assert len(lst) == 2

    # PATCH 更新现值
    r3 = auth_client.patch(f"/api/investment/assets/{asset_id}", json={"current_value": 1900})
    assert r3.status_code == 200

    # portfolio 总览
    summary = auth_client.get("/api/investment/portfolio").get_json()
    assert summary["total_value"] == 1900 + 2000
    assert summary["asset_count"] == 2
    pct_sum = sum(r["pct"] for r in summary["allocation"]["by_type"])
    assert abs(pct_sum - 100.0) < 0.1

    # 删除
    r4 = auth_client.delete(f"/api/investment/assets/{asset_id}")
    assert r4.status_code == 200


def test_asset_invalid_type_rejected(auth_client):
    r = auth_client.post("/api/investment/assets", json={"name": "X", "type": "bogus"})
    assert r.status_code == 400


def test_goal_crud(auth_client):
    r = auth_client.post("/api/investment/goals", json={
        "name": "买房首付", "target_amount": 500000, "deadline": "2030-12-31",
        "current_progress": 80000,
    })
    assert r.status_code == 201
    gid = r.get_json()["id"]

    lst = auth_client.get("/api/investment/goals").get_json()
    assert any(g["id"] == gid for g in lst)

    r2 = auth_client.patch(f"/api/investment/goals/{gid}", json={"current_progress": 100000})
    assert r2.status_code == 200

    r3 = auth_client.delete(f"/api/investment/goals/{gid}")
    assert r3.status_code == 200


def test_goal_requires_positive_target(auth_client):
    r = auth_client.post("/api/investment/goals", json={"name": "X", "target_amount": 0})
    assert r.status_code == 400


def test_transaction_rejects_foreign_asset(auth_client):
    r = auth_client.post("/api/investment/transactions", json={
        "asset_id": 9999, "kind": "buy", "quantity": 1, "price": 10, "date": "2026-04-01",
    })
    assert r.status_code == 404


def test_portfolio_empty(auth_client):
    data = auth_client.get("/api/investment/portfolio").get_json()
    assert data["total_value"] == 0
    assert data["asset_count"] == 0


def test_risk_quiz_get_returns_questions(auth_client):
    data = auth_client.get("/api/investment/risk-quiz").get_json()
    assert len(data["questions"]) == 5
    assert data["profile"] is None
