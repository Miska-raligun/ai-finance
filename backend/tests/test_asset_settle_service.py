"""services/asset_settle 纯函数测试：route + MCP 共用入口的核心结算逻辑。

route 端到端用例已经在 test_asset_settle.py 覆盖；这里盯纯函数行为，
保证 MCP 工具走相同函数也得到一致结果。
"""
import sqlite3
from datetime import datetime

import pytest


@pytest.fixture
def conn(temp_db):
    """复用 conftest 的 temp_db 路径，给纯 sqlite 连接做测试。"""
    import db as db_mod
    db_mod.init_db()
    c = sqlite3.connect(db_mod.DB_FILE)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _seed(conn, *, holdings=10, cost_basis=15000, current_value=18000):
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO users (id, username, password) VALUES (1, 'tester', 'x')"
    )
    conn.execute(
        "INSERT INTO asset_types (user_id, name, shape, quote_source, created_at) "
        "VALUES (1, 'A股', 'security_manual', NULL, ?)", (now,))
    cur = conn.execute(
        "INSERT INTO assets (user_id, name, type, symbol, holdings, cost_basis, "
        "current_value, currency, created_at, updated_at) "
        "VALUES (1, '茅台', 'A股', 'sh600519', ?, ?, ?, 'CNY', ?, ?)",
        (holdings, cost_basis, current_value, now, now),
    )
    conn.commit()
    return cur.lastrowid


def test_sell_full_profit(conn):
    aid = _seed(conn)
    from services.asset_settle import sell_asset
    r = sell_asset(conn, 1, aid, price=1900, fee=5, date="2025-04-15")
    assert r["ledger"] == "income"
    assert abs(r["pnl"] - 3995.0) < 0.01
    assert r["remaining_holdings"] == 0
    income = conn.execute("SELECT category, amount FROM income").fetchone()
    assert income["category"] == "投资盈利"
    assert abs(income["amount"] - 3995.0) < 0.01


def test_sell_partial_loss_keeps_asset(conn):
    aid = _seed(conn, holdings=10, cost_basis=15000)
    from services.asset_settle import sell_asset
    r = sell_asset(conn, 1, aid, price=1300, quantity=4)
    assert r["ledger"] == "expense"
    assert abs(r["remaining_holdings"] - 6) < 1e-6
    asset = conn.execute("SELECT holdings, cost_basis FROM assets").fetchone()
    assert abs(asset["holdings"] - 6) < 1e-6
    assert abs(asset["cost_basis"] - 9000.0) < 0.01


def test_sell_invalid_inputs_raise(conn):
    aid = _seed(conn)
    from services.asset_settle import sell_asset, SettleError
    with pytest.raises(SettleError):
        sell_asset(conn, 1, aid, price=0)
    with pytest.raises(SettleError):
        sell_asset(conn, 1, aid, price=10, quantity=9999)
    with pytest.raises(SettleError):
        sell_asset(conn, 1, 99999, price=10)


def test_archive_records_income(conn):
    aid = _seed(conn, cost_basis=10000, current_value=12500)
    from services.asset_settle import archive_asset
    r = archive_asset(conn, 1, aid, date="2025-04-20", note="停止追踪")
    assert r["ledger"] == "income"
    assert abs(r["pnl"] - 2500.0) < 0.01
    income = conn.execute("SELECT note FROM income").fetchone()
    assert "归档" in income["note"]
    assert "停止追踪" in income["note"]


def test_archive_break_even(conn):
    aid = _seed(conn, cost_basis=8000, current_value=8000)
    from services.asset_settle import archive_asset
    r = archive_asset(conn, 1, aid)
    assert r["ledger"] == "none"
    assert conn.execute("SELECT COUNT(*) FROM income").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 0
