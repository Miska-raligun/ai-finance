"""验证迁移系统幂等性 + Sprint 1 新表结构。"""
import sqlite3


def test_migrations_create_schema_version(temp_db):
    import db as db_mod
    db_mod.init_db()

    conn = sqlite3.connect(temp_db)
    rows = conn.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
    versions = {r[0] for r in rows}
    assert 0 in versions, "baseline 0000 必须被记录"
    assert 3 in versions, "ops 0003 必须被记录"
    conn.close()


def test_llm_usage_table_exists(temp_db):
    import db as db_mod
    db_mod.init_db()

    conn = sqlite3.connect(temp_db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(llm_usage)").fetchall()}
    assert {"user_id", "endpoint", "model", "prompt_tokens", "total_tokens"} <= cols
    conn.close()


def test_migrations_idempotent(temp_db):
    import db as db_mod
    db_mod.init_db()
    db_mod.init_db()  # 再跑一次不应报错或重复插入版本号

    conn = sqlite3.connect(temp_db)
    rows = conn.execute("SELECT version FROM schema_version").fetchall()
    versions = [r[0] for r in rows]
    assert len(versions) == len(set(versions)), "schema_version 不应重复"
    conn.close()
