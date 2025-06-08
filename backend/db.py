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
    cur.execute("DROP TABLE IF EXISTS records")
    cur.execute("DROP TABLE IF EXISTS budgets")
    cur.execute("DROP TABLE IF EXISTS categories")
    # 记录支出
    cur.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            amount REAL,
            note TEXT,
            date TEXT
        )
    """)

    # 分类预算，默认月度预算
    cur.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT UNIQUE,
            amount REAL,
            cycle TEXT DEFAULT 'monthly'
        )
    """)

    # 支出分类
    cur.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    """)

    conn.commit()
    conn.close()
