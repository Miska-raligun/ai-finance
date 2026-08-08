"""卖出 / 归档资产：盈亏自动结算到 income / records。"""
from datetime import datetime


def _seed_asset(app, uid, *, name="贵州茅台", atype="A股", holdings=10,
                cost_basis=15000.0, current_value=18000.0):
    """直接插入资产 + 类型，绕开行情拉取和创建校验。"""
    from db import get_db
    with app.app_context():
        db = get_db()
        # 类型也得有
        db.execute(
            "INSERT INTO asset_types (user_id, name, shape, quote_source, created_at) "
            "VALUES (?, ?, 'security_manual', NULL, ?)",
            (uid, atype, datetime.now().isoformat(timespec="seconds")),
        )
        cur = db.execute(
            "INSERT INTO assets (user_id, name, type, symbol, holdings, "
            "cost_basis, current_value, currency, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'CNY', NULL, ?, ?)",
            (uid, name, atype, "sh600519", holdings, cost_basis, current_value,
             datetime.now().isoformat(timespec="seconds"),
             datetime.now().isoformat(timespec="seconds")),
        )
        db.commit()
        return cur.lastrowid


def test_sell_full_with_profit_records_income(auth_client, app):
    """全部卖出 + 盈利 → income 表收到一笔『投资盈利』记录。"""
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    asset_id = _seed_asset(app, uid, holdings=10, cost_basis=15000, current_value=18000)

    r = auth_client.post(
        f"/api/investment/assets/{asset_id}/sell",
        json={"price": 1900, "fee": 5, "date": "2025-04-15"},
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["success"] is True
    # proceeds = 1900*10 - 5 = 18995；cost = 15000；pnl = 3995
    assert abs(body["pnl"] - 3995.0) < 0.01
    assert body["ledger"] == "income"
    assert body["remaining_holdings"] == 0

    from db import get_db
    with app.app_context():
        income = get_db().execute(
            "SELECT category, amount, note, date FROM income WHERE user_id = ?",
            (uid,),
        ).fetchone()
        assert income is not None
        assert income["category"] == "投资盈利"
        assert abs(income["amount"] - 3995.0) < 0.01
        assert income["date"] == "2025-04-15"
        # 备注必须能定位到资产 + 关键金额
        assert "贵州茅台" in income["note"]
        assert "成本" in income["note"]
        assert "卖出" in income["note"]

        # 资产应已被删除（全部卖出）
        cnt = get_db().execute(
            "SELECT COUNT(*) FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()[0]
        assert cnt == 0


def test_sell_partial_with_loss_records_expense(auth_client, app):
    """部分卖出 + 亏损 → records 表收到『投资亏损』，剩余持仓 + 摊销成本。"""
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    asset_id = _seed_asset(app, uid, holdings=10, cost_basis=15000, current_value=18000)

    r = auth_client.post(
        f"/api/investment/assets/{asset_id}/sell",
        json={"price": 1300, "quantity": 4, "fee": 0, "date": "2025-04-16"},
    )
    body = r.get_json()
    # proceeds = 1300*4 = 5200；prorata cost = 15000*0.4 = 6000；pnl = -800
    assert body["ledger"] == "expense"
    assert abs(body["pnl"] - (-800.0)) < 0.01
    assert abs(body["remaining_holdings"] - 6) < 1e-6

    from db import get_db
    with app.app_context():
        rec = get_db().execute(
            "SELECT category, amount FROM records WHERE user_id = ?",
            (uid,),
        ).fetchone()
        assert rec["category"] == "投资亏损"
        assert abs(rec["amount"] - 800.0) < 0.01

        # 资产仍在；持仓 / 成本按比例减
        a = get_db().execute(
            "SELECT holdings, cost_basis, current_value FROM assets WHERE id = ?",
            (asset_id,),
        ).fetchone()
        assert abs(a["holdings"] - 6) < 1e-6
        assert abs(a["cost_basis"] - 9000.0) < 0.01  # 15000 - 6000
        assert abs(a["current_value"] - 10800.0) < 0.01  # 18000 * 6/10


def test_sell_validates_inputs(auth_client, app):
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    asset_id = _seed_asset(app, uid)

    # 价格为 0
    r = auth_client.post(f"/api/investment/assets/{asset_id}/sell", json={"price": 0})
    assert r.status_code == 400

    # 数量超过持仓
    r = auth_client.post(
        f"/api/investment/assets/{asset_id}/sell",
        json={"price": 100, "quantity": 9999},
    )
    assert r.status_code == 400


def test_archive_settles_with_current_value(auth_client, app):
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    asset_id = _seed_asset(app, uid, cost_basis=10000, current_value=12500)

    r = auth_client.post(
        f"/api/investment/assets/{asset_id}/archive",
        json={"date": "2025-04-20", "note": "停止追踪"},
    )
    body = r.get_json()
    assert body["success"] is True
    assert body["ledger"] == "income"
    assert abs(body["pnl"] - 2500.0) < 0.01

    from db import get_db
    with app.app_context():
        income = get_db().execute(
            "SELECT category, amount, note FROM income WHERE user_id = ?",
            (uid,),
        ).fetchone()
        assert income["category"] == "投资盈利"
        assert abs(income["amount"] - 2500.0) < 0.01
        assert "归档" in income["note"]
        assert "停止追踪" in income["note"]

        # 资产被删
        cnt = get_db().execute(
            "SELECT COUNT(*) FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()[0]
        assert cnt == 0


def test_archive_break_even_skips_ledger(auth_client, app):
    """成本 = 现值 时 pnl ≈ 0，不应写任何记录避免噪音。"""
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    asset_id = _seed_asset(app, uid, cost_basis=8000, current_value=8000)

    r = auth_client.post(f"/api/investment/assets/{asset_id}/archive", json={})
    body = r.get_json()
    assert body["ledger"] == "none"
    assert abs(body["pnl"]) < 0.01

    from db import get_db
    with app.app_context():
        income_cnt = get_db().execute(
            "SELECT COUNT(*) FROM income WHERE user_id = ?", (uid,)
        ).fetchone()[0]
        rec_cnt = get_db().execute(
            "SELECT COUNT(*) FROM records WHERE user_id = ?", (uid,)
        ).fetchone()[0]
        assert income_cnt == 0
        assert rec_cnt == 0
