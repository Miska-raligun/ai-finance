"""资产市值历史快照：refresh 时写入 + history 端点查询。"""
import sqlite3
from datetime import datetime


def _seed_asset_type(conn, uid, name="A股"):
    conn.execute(
        "INSERT INTO asset_types (user_id, name, shape, quote_source, created_at) "
        "VALUES (?, ?, 'security_manual', NULL, ?)",
        (uid, name, datetime.now().isoformat(timespec="seconds")),
    )


def test_apply_new_value_writes_history_row(auth_client, app):
    """直接调 _apply_new_value 应在 history 表写入一条快照。"""
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    with app.app_context():
        from db import get_db
        from services.quotes import _apply_new_value
        db = get_db()
        _seed_asset_type(db, uid)
        db.execute(
            "INSERT INTO assets (id, user_id, name, type, holdings, cost_basis, "
            "current_value, currency, created_at, updated_at) "
            "VALUES (1, ?, 'AAPL', 'A股', 10, 1000, 1200, 'CNY', ?, ?)",
            (uid, datetime.now().isoformat(), datetime.now().isoformat()),
        )
        db.commit()

        _apply_new_value(db, uid, 1, 1500.0)
        db.commit()

        row = db.execute(
            "SELECT user_id, asset_id, value FROM asset_value_history "
            "WHERE asset_id = ?", (1,)
        ).fetchone()
        assert row is not None
        assert row["user_id"] == uid
        assert abs(row["value"] - 1500.0) < 0.01


def test_apply_new_value_dedup_within_same_day(auth_client, app):
    """同天多次刷新只保留最后一条快照，避免行情频繁刷新时表膨胀。"""
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    with app.app_context():
        from db import get_db
        from services.quotes import _apply_new_value
        db = get_db()
        _seed_asset_type(db, uid)
        db.execute(
            "INSERT INTO assets (id, user_id, name, type, holdings, cost_basis, "
            "current_value, currency, created_at, updated_at) "
            "VALUES (2, ?, 'BTC', 'A股', 1, 10000, 12000, 'CNY', ?, ?)",
            (uid, datetime.now().isoformat(), datetime.now().isoformat()),
        )
        db.commit()

        _apply_new_value(db, uid, 2, 11000.0)
        _apply_new_value(db, uid, 2, 11500.0)
        _apply_new_value(db, uid, 2, 12500.0)
        db.commit()

        rows = db.execute(
            "SELECT value FROM asset_value_history WHERE asset_id = ?",
            (2,),
        ).fetchall()
        assert len(rows) == 1
        assert abs(rows[0]["value"] - 12500.0) < 0.01


def test_history_endpoint_returns_points(auth_client, app):
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    with app.app_context():
        from db import get_db
        db = get_db()
        _seed_asset_type(db, uid)
        db.execute(
            "INSERT INTO assets (id, user_id, name, type, holdings, cost_basis, "
            "current_value, currency, created_at, updated_at) "
            "VALUES (3, ?, '茅台', 'A股', 5, 8000, 9000, 'CNY', ?, ?)",
            (uid, datetime.now().isoformat(), datetime.now().isoformat()),
        )
        # 3 天前 / 2 天前 / 今天 各一条
        db.execute(
            "INSERT INTO asset_value_history (user_id, asset_id, value, recorded_at) "
            "VALUES (?, 3, 8500, date('now', '-3 days'))", (uid,),
        )
        db.execute(
            "INSERT INTO asset_value_history (user_id, asset_id, value, recorded_at) "
            "VALUES (?, 3, 8800, date('now', '-2 days'))", (uid,),
        )
        db.execute(
            "INSERT INTO asset_value_history (user_id, asset_id, value, recorded_at) "
            "VALUES (?, 3, 9000, date('now'))", (uid,),
        )
        db.commit()

    r = auth_client.get("/api/investment/assets/3/history?days=30")
    assert r.status_code == 200
    body = r.get_json()
    assert body["asset_id"] == 3
    assert body["asset_name"] == "茅台"
    assert len(body["points"]) == 3
    # 按 recorded_at 升序
    assert body["points"][0]["value"] == 8500
    assert body["points"][-1]["value"] == 9000


def test_history_endpoint_404_for_others_asset(auth_client, app):
    """不能拉别人的资产历史。"""
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    with app.app_context():
        from db import get_db
        db = get_db()
        # 制造一个别人的用户和资产
        db.execute("INSERT INTO users (id, username, password) VALUES (9999, 'other', 'x')")
        _seed_asset_type(db, 9999, "A股")
        db.execute(
            "INSERT INTO assets (id, user_id, name, type, holdings, cost_basis, "
            "current_value, currency, created_at, updated_at) "
            "VALUES (4, 9999, 'SECRET', 'A股', 1, 100, 200, 'CNY', ?, ?)",
            (datetime.now().isoformat(), datetime.now().isoformat()),
        )
        db.commit()

    r = auth_client.get("/api/investment/assets/4/history?days=7")
    assert r.status_code == 404


def test_history_days_clamped(auth_client, app):
    """days 参数应被 clamp 到 1..365。"""
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    with app.app_context():
        from db import get_db
        db = get_db()
        _seed_asset_type(db, uid)
        db.execute(
            "INSERT INTO assets (id, user_id, name, type, holdings, cost_basis, "
            "current_value, currency, created_at, updated_at) "
            "VALUES (5, ?, 'TEST', 'A股', 1, 100, 200, 'CNY', ?, ?)",
            (uid, datetime.now().isoformat(), datetime.now().isoformat()),
        )
        db.commit()

    r = auth_client.get("/api/investment/assets/5/history?days=99999")
    assert r.status_code == 200
    assert r.get_json()["days"] == 365

    r = auth_client.get("/api/investment/assets/5/history?days=-5")
    assert r.status_code == 200
    assert r.get_json()["days"] == 1
