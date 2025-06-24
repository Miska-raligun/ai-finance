import sqlite3

DB_FILE = 'records.db'

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def column_exists(cur, table, column):
    """Check if a column exists in a SQLite table."""
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def init_db():
    conn = get_db()
    cur = conn.cursor()

    # ✅ 每次启动清空所有表（调试用）
    #cur.execute("DROP TABLE IF EXISTS records")
    #cur.execute("DROP TABLE IF EXISTS budgets")
    #cur.execute("DROP TABLE IF EXISTS categories")
    #cur.execute("DROP TABLE IF EXISTS income")  
    #cur.execute("DROP TABLE IF EXISTS users")

    # ✅ 支出记录表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT,
            amount REAL,
            note TEXT,
            date TEXT,
            month TEXT,  -- 格式如 "2025-06"
            year TEXT
        )
    """)

    # ✅ 预算设置表（按月）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT,
            amount REAL,
            cycle TEXT DEFAULT 'monthly',
            month TEXT,
            UNIQUE(category, month, user_id)
        )
    """)

    # ✅ 支出分类表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            type TEXT CHECK(type IN ('支出', '收入')) DEFAULT '支出',
            UNIQUE(name, user_id)
        )
    """)

    # ✅ 收入记录表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS income (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT,     -- 收入来源分类名（如“工资”、“奖金”等）
            amount REAL,       -- 收入金额
            note TEXT,         -- 备注（可选）
            date TEXT,         -- 精确日期（如“2025-06-10”）
            month TEXT,        -- 月份（如“2025-06”）
            year TEXT          -- 年份（如“2025”）
        )
    """)

    # ✅ 用户表
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            is_admin INTEGER DEFAULT 0
        )
    """
    )

    # ✅ LLM 配置表，每个用户一条记录
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_config (
            user_id INTEGER PRIMARY KEY,
            url TEXT,
            apikey TEXT,
            model TEXT,
            persona TEXT
        )
    """
    )

    # ✅ 补充缺失的 is_admin 字段（向后兼容）
    if not column_exists(cur, "users", "is_admin"):
        cur.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")

    # 兼容旧版数据库，补充缺失的 user_id 字段
    for tbl in ("records", "budgets", "categories", "income"):
        if not column_exists(cur, tbl, "user_id"):
            cur.execute(f"ALTER TABLE {tbl} ADD COLUMN user_id INTEGER")

    admin_row = cur.execute(
        "SELECT id FROM users WHERE username = ? AND is_admin = 1", ("admin",)
    ).fetchone()

    if not admin_row:
        from werkzeug.security import generate_password_hash

        # ⚠️ 确保不会因为已有非管理员 admin 用户而报错
        cur.execute("SELECT id FROM users WHERE username = ?", ("admin",))
        existing_user = cur.fetchone()

        if existing_user:
            print("⚠️ 已存在名为 admin 的用户，无法创建默认管理员。请手动检查权限。")
        else:
            cur.execute(
                "INSERT INTO users (username, password, is_admin) VALUES (?, ?, 1)",
                ("admin", generate_password_hash("admin")),
            )


    conn.commit()
    conn.close()

