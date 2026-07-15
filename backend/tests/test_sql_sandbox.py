"""SQL 沙箱:表达力(聚合直接算)与安全边界(行隔离/表隔离/只读)。"""
from __future__ import annotations

import sqlite3

import pytest

from services.sql_sandbox import run_readonly_query, SandboxError


@pytest.fixture
def seeded(app, temp_db):
    """两个用户各有记录:验证行级隔离必须要有'别人的数据'。"""
    conn = sqlite3.connect(temp_db)
    rows = [
        (1, "餐饮", 38.5, "盒马买菜", "2026-07-01", None),
        (1, "餐饮", 61.5, "盒马鲜生囤货", "2026-07-05", None),
        (1, "交通", 12.0, "地铁", "2026-07-05", None),
        (1, "餐饮", 999.0, "已删除的盒马订单", "2026-07-06", "2026-07-07T00:00:00"),
        (2, "餐饮", 500.0, "盒马-别人的", "2026-07-02", None),
    ]
    conn.executemany(
        "INSERT INTO records (user_id, category, amount, note, date, deleted_at) "
        "VALUES (?, ?, ?, ?, ?, ?)", rows,
    )
    conn.commit()
    conn.close()
    return temp_db


def test_aggregate_in_one_query(seeded):
    """「盒马总共花了多少」一条 SQL 出结果——这就是开这个工具的意义。"""
    cols, rows, trunc = run_readonly_query(
        1, "SELECT COUNT(*) AS n, SUM(amount) AS total FROM my_records WHERE note LIKE '%盒马%'",
        db_file=seeded,
    )
    assert cols == ["n", "total"]
    # 只算自己的 2 笔(软删的 999 和 user2 的 500 都不在)
    assert rows == [(2, 100.0)]
    assert trunc is False


def test_row_isolation_between_users(seeded):
    _, rows, _ = run_readonly_query(2, "SELECT SUM(amount) FROM my_records", db_file=seeded)
    assert rows == [(500.0,)]


def test_soft_deleted_rows_invisible(seeded):
    _, rows, _ = run_readonly_query(
        1, "SELECT COUNT(*) FROM my_records WHERE amount = 999", db_file=seeded)
    assert rows == [(0,)]


def test_direct_table_access_denied(seeded):
    for evil in (
        "SELECT * FROM records",                    # 绕开视图读真实表
        "SELECT password FROM users",               # 敏感表
        "SELECT apikey FROM llm_config",            # 敏感表
        "SELECT * FROM sqlite_master",              # 摸 schema
    ):
        with pytest.raises(SandboxError):
            run_readonly_query(1, evil, db_file=seeded)


def test_writes_and_ddl_rejected(seeded):
    for evil in (
        "INSERT INTO records (user_id, amount) VALUES (1, 1)",
        "DELETE FROM records",
        "UPDATE records SET amount = 0",
        "DROP TABLE records",
        "PRAGMA journal_mode = DELETE",
        "SELECT 1; DELETE FROM records",            # 多语句
    ):
        with pytest.raises(SandboxError):
            run_readonly_query(1, evil, db_file=seeded)
    # 沙箱跑完后数据完好
    conn = sqlite3.connect(seeded)
    assert conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 5
    conn.close()


def test_with_cte_and_month_grouping(seeded):
    cols, rows, _ = run_readonly_query(
        1,
        "WITH m AS (SELECT strftime('%Y-%m', date) AS month, amount FROM my_records) "
        "SELECT month, SUM(amount) FROM m GROUP BY month",
        db_file=seeded,
    )
    assert rows == [("2026-07", 112.0)]


def test_truncation(seeded):
    conn = sqlite3.connect(seeded)
    conn.executemany(
        "INSERT INTO records (user_id, category, amount, note, date) VALUES (1,'x',1,'r','2026-07-01')",
        [() for _ in range(30)],
    )
    conn.commit(); conn.close()
    _, rows, trunc = run_readonly_query(
        1, "SELECT id FROM my_records", db_file=seeded, max_rows=10)
    assert len(rows) == 10
    assert trunc is True
