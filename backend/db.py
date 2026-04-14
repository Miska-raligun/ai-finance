import sqlite3
import logging

DB_FILE = 'records.db'
logger = logging.getLogger(__name__)


def get_db():
    """在 Flask 请求上下文中复用连接并自动关闭；Flask 外返回独立连接（调用方需自行关闭）"""
    try:
        from flask import g, has_app_context
        if has_app_context():
            if 'db' not in g:
                g.db = sqlite3.connect(DB_FILE)
                g.db.row_factory = sqlite3.Row
            return g.db
    except ImportError:
        pass
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def close_db(e=None):
    """Flask teardown 回调，自动关闭请求级连接"""
    try:
        from flask import g
        db = g.pop('db', None)
        if db is not None:
            db.close()
    except ImportError:
        pass


def init_app(app):
    """注册 teardown 回调，在 app.py 中调用"""
    app.teardown_appcontext(close_db)

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
            date TEXT
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
            category TEXT,
            amount REAL,
            note TEXT,
            date TEXT
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

    # ✅ 聊天记录表，保存每个用户最近10条对话
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            content TEXT
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

    # 迁移：移除 records/income 表中冗余的 month/year 列（SQLite 3.35+）
    for tbl in ("records", "income"):
        if column_exists(cur, tbl, "month"):
            cur.execute(f"ALTER TABLE {tbl} DROP COLUMN month")
        if column_exists(cur, tbl, "year"):
            cur.execute(f"ALTER TABLE {tbl} DROP COLUMN year")

    # ✅ 索引：加速按用户+日期、用户+分类的常用查询
    cur.execute("CREATE INDEX IF NOT EXISTS idx_records_user_date ON records(user_id, date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_records_user_cat ON records(user_id, category)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_income_user_date ON income(user_id, date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_income_user_cat ON income(user_id, category)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_budgets_user_month ON budgets(user_id, month)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_budgets_user_month_cat ON budgets(user_id, month, category)")

    admin_row = cur.execute(
        "SELECT id FROM users WHERE username = ? AND is_admin = 1", ("admin",)
    ).fetchone()

    if not admin_row:
        from werkzeug.security import generate_password_hash

        # ⚠️ 确保不会因为已有非管理员 admin 用户而报错
        cur.execute("SELECT id FROM users WHERE username = ?", ("admin",))
        existing_user = cur.fetchone()

        if existing_user:
            logger.warning("已存在名为 admin 的用户，无法创建默认管理员，请手动检查权限。")
        else:
            cur.execute(
                "INSERT INTO users (username, password, is_admin) VALUES (?, ?, 1)",
                ("admin", generate_password_hash("admin")),
            )


    conn.commit()
    conn.close()


def add_chat_message(user_id: int, role: str, content: str):
    """Insert a chat message and keep only the latest 50 records for the user."""
    db = get_db()
    db.execute(
        "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
        (user_id, role, content),
    )
    db.execute(
        """
        DELETE FROM chat_history
        WHERE user_id = ? AND id NOT IN (
            SELECT id FROM chat_history WHERE user_id = ? ORDER BY id DESC LIMIT 50
        )
        """,
        (user_id, user_id),
    )
    db.commit()


def get_chat_history(user_id: int):
    """Return the chat history list for the user ordered by id."""
    db = get_db()
    rows = db.execute(
        "SELECT role, content FROM chat_history WHERE user_id = ? ORDER BY id",
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def cleanup_empty_category(user_id: int, category: str):
    """删除指定用户下没有任何记录的分类（及关联预算）。"""
    db = get_db()
    has_records = db.execute(
        "SELECT 1 FROM records WHERE user_id = ? AND category = ? LIMIT 1",
        (user_id, category),
    ).fetchone()
    if has_records:
        return
    has_income = db.execute(
        "SELECT 1 FROM income WHERE user_id = ? AND category = ? LIMIT 1",
        (user_id, category),
    ).fetchone()
    if has_income:
        return
    db.execute("DELETE FROM budgets WHERE user_id = ? AND category = ?", (user_id, category))
    db.execute("DELETE FROM categories WHERE user_id = ? AND name = ?", (user_id, category))
    db.commit()


def cleanup_all_empty_categories():
    """启动时清理所有用户下没有任何记录的分类。"""
    db = get_db()
    db.execute("""
        DELETE FROM budgets WHERE NOT EXISTS (
            SELECT 1 FROM categories
            WHERE categories.user_id = budgets.user_id AND categories.name = budgets.category
        )
    """)
    db.execute("""
        DELETE FROM categories WHERE type = '支出' AND NOT EXISTS (
            SELECT 1 FROM records
            WHERE records.user_id = categories.user_id AND records.category = categories.name
        )
    """)
    db.execute("""
        DELETE FROM categories WHERE type = '收入' AND NOT EXISTS (
            SELECT 1 FROM income
            WHERE income.user_id = categories.user_id AND income.category = categories.name
        )
    """)
    db.commit()

