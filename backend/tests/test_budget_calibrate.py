"""预算自动校准：3 月均值 × inflation 计算 + apply 端点。"""
from datetime import datetime


def _seed_records(app, uid, items):
    from db import get_db
    with app.app_context():
        db = get_db()
        for cat, amt, date in items:
            db.execute(
                "INSERT INTO records (user_id, category, amount, note, date) "
                "VALUES (?, ?, ?, '', ?)",
                (uid, cat, amt, date),
            )
        # 用上面的分类自动建好类型
        for cat, _, _ in items:
            db.execute(
                "INSERT OR IGNORE INTO categories (user_id, name, type) "
                "VALUES (?, ?, '支出')", (uid, cat),
            )
        db.commit()


def test_calibrate_basic_average(auth_client, app):
    """3 月内餐饮共 ¥1500，分布在 3 个月，均值 500，× 1.05 = 525 上取整。"""
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    _seed_records(app, uid, [
        ("餐饮", 500, "2025-01-15"),
        ("餐饮", 500, "2025-02-15"),
        ("餐饮", 500, "2025-03-15"),
    ])
    r = auth_client.get("/api/budgets/calibrate?month=2025-04&inflation=1.05")
    assert r.status_code == 200
    body = r.get_json()
    assert body["target_month"] == "2025-04"
    item = next((x for x in body["items"] if x["category"] == "餐饮"), None)
    assert item is not None
    assert abs(item["avg_spend_3m"] - 500) < 0.01
    assert item["suggested_budget"] == 525   # ceil(500 * 1.05)
    assert item["active_months"] == 3


def test_calibrate_with_active_months_below_3(auth_client, app):
    """只有 1 个月有数据时，按那 1 个月平均，不再除以 3。"""
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    _seed_records(app, uid, [
        ("交通", 200, "2025-03-15"),
    ])
    r = auth_client.get("/api/budgets/calibrate?month=2025-04&inflation=1.0")
    item = next((x for x in r.get_json()["items"] if x["category"] == "交通"), None)
    assert item is not None
    assert item["active_months"] == 1
    assert item["suggested_budget"] == 200


def test_calibrate_default_target_is_next_month(auth_client, app):
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    _seed_records(app, uid, [("水电", 100, "2025-01-01")])
    r = auth_client.get("/api/budgets/calibrate")
    body = r.get_json()
    today = datetime.now()
    year, mon = today.year, today.month
    expected = f"{year + 1}-01" if mon == 12 else f"{year}-{mon + 1:02d}"
    assert body["target_month"] == expected


def test_apply_calibration_writes_budgets(auth_client, app):
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    _seed_records(app, uid, [("餐饮", 500, "2025-02-15")])  # 让分类存在

    r = auth_client.post("/api/budgets/calibrate/apply", json={
        "month": "2025-04",
        "items": [
            {"category": "餐饮", "suggested_budget": 525},
            {"category": "幽灵分类", "suggested_budget": 100},  # 不存在，应跳过
        ],
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body["applied"] == 1   # 只成功写了 1 条

    from db import get_db
    with app.app_context():
        row = get_db().execute(
            "SELECT amount FROM budgets WHERE user_id=? AND category=? AND month=?",
            (uid, "餐饮", "2025-04"),
        ).fetchone()
        assert row is not None
        assert abs(row["amount"] - 525) < 0.01


def test_apply_rejects_empty_items(auth_client):
    r = auth_client.post("/api/budgets/calibrate/apply", json={"month": "2025-04", "items": []})
    assert r.status_code == 400


def test_calibrate_bad_month_format(auth_client):
    r = auth_client.get("/api/budgets/calibrate?month=2025/04")
    assert r.status_code == 400
