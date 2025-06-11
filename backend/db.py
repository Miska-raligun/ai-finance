import sqlite3

DB_FILE = 'records.db'

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    # ✅ 每次启动清空所有表（调试用）
    #cur.execute("DROP TABLE IF EXISTS records")
    #cur.execute("DROP TABLE IF EXISTS budgets")
    #cur.execute("DROP TABLE IF EXISTS categories")
    #cur.execute("DROP TABLE IF EXISTS income")  # 👈 清除旧收入表（调试用）

    # ✅ 支出记录表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            category TEXT,
            amount REAL,
            cycle TEXT DEFAULT 'monthly',
            month TEXT,
            UNIQUE(category, month)
        )
    """)

    # ✅ 支出分类表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            type TEXT CHECK(type IN ('支出', '收入')) DEFAULT '支出'
        )
    """)

    # ✅ 收入记录表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS income (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            password TEXT
        )
    """
    )

    conn.commit()
    conn.close()

