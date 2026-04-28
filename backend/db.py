import os
import sqlite3
import logging
from datetime import datetime

DB_FILE = os.getenv('DB_FILE', 'records.db')
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


def _persist_initial_admin_password(password: str) -> None:
    """把首启随机管理员密码写入 logs/initial_admin.txt（0600）。"""
    try:
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, "initial_admin.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(
                "默认管理员账号 admin 的初始密码（首次登录后请立即修改并删除本文件）：\n"
                f"{password}\n"
            )
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except Exception as e:
        logger.error("写入初始管理员密码文件失败：%s（请查看 stderr 中的随机密码）", e)
        logger.error("INITIAL ADMIN PASSWORD: %s", password)

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
    # 累计支出窗口函数 SUM() OVER (PARTITION BY user_id, category ORDER BY date, id) 的覆盖索引
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_records_user_cat_date_id ON records(user_id, category, date, id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_history_user ON chat_history(user_id, id)"
    )

    admin_row = cur.execute(
        "SELECT id FROM users WHERE username = ? AND is_admin = 1", ("admin",)
    ).fetchone()

    if not admin_row:
        from werkzeug.security import generate_password_hash
        import secrets as _secrets

        # ⚠️ 确保不会因为已有非管理员 admin 用户而报错
        cur.execute("SELECT id FROM users WHERE username = ?", ("admin",))
        existing_user = cur.fetchone()

        if existing_user:
            logger.warning("已存在名为 admin 的用户，无法创建默认管理员，请手动检查权限。")
        else:
            # 安全：不再使用固定的 admin/admin。允许通过 INITIAL_ADMIN_PASSWORD
            # 显式指定，否则随机生成 16 字节密码并写入 logs/initial_admin.txt（0600）。
            initial_pw = os.getenv("INITIAL_ADMIN_PASSWORD", "").strip()
            if not initial_pw:
                initial_pw = _secrets.token_urlsafe(16)
                _persist_initial_admin_password(initial_pw)
            cur.execute(
                "INSERT INTO users (username, password, is_admin) VALUES (?, ?, 1)",
                ("admin", generate_password_hash(initial_pw)),
            )
            logger.warning(
                "已创建默认管理员 admin。初始密码已写入 logs/initial_admin.txt，"
                "请尽快登录并修改后删除该文件。"
            )


    conn.commit()

    # 应用增量迁移（baseline 对老库幂等无副作用，新版本表按需创建）
    try:
        from migrations import apply_migrations
        apply_migrations(conn)
    except Exception as e:
        logger.error("迁移执行失败：%s", e)

    # 启动后回填：把历史明文存储的 llm_config.apikey 升级为加密格式。
    # 完全幂等——已加密的行（带 enc:v1: 前缀）会被 crypto.encrypt_secret 自动跳过。
    try:
        _backfill_encrypt_llm_keys(conn)
    except Exception as e:
        logger.error("LLM key 加密回填失败（不影响启动）：%s", e)
    finally:
        conn.close()


def _backfill_encrypt_llm_keys(conn) -> None:
    """把 llm_config.apikey 中的历史明文逐条加密回写。"""
    rows = conn.execute("SELECT user_id, apikey FROM llm_config").fetchall()
    if not rows:
        return
    from crypto import encrypt_secret
    upgraded = 0
    for r in rows:
        key = r["apikey"] if isinstance(r, sqlite3.Row) else r[1]
        uid = r["user_id"] if isinstance(r, sqlite3.Row) else r[0]
        if not key:
            continue
        if str(key).startswith("enc:v1:"):
            continue
        conn.execute(
            "UPDATE llm_config SET apikey = ? WHERE user_id = ?",
            (encrypt_secret(str(key)), uid),
        )
        upgraded += 1
    if upgraded:
        conn.commit()
        logger.warning("LLM key 加密回填：升级了 %d 条历史明文记录", upgraded)


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


# 外键 / 级联清理 ------------------------------------------------------------
# SQLite 默认 PRAGMA foreign_keys = OFF，且历史 schema 也没声明 FK。直接给所有
# 表加 FK 需要重建表，风险大；改为提供单点入口，让 admin/账号注销/合规请求都
# 走同一份级联逻辑，避免散落各处的"忘了删 X 表"。
_USER_DATA_TABLES = (
    "records",
    "income",
    "categories",
    "budgets",
    "llm_config",
    "chat_history",
    "assets",
    "asset_transactions",
    "asset_types",
    "financial_goals",
    "risk_profiles",
    "monthly_reports",
    "user_profiles",
    "rebalance_cache",
    "llm_usage",
)


def purge_user_data(user_ids: list[int]) -> dict[str, int]:
    """物理删除指定用户在所有业务表里的痕迹。返回 {table: rowcount}。

    仅在以下场景使用：管理员批量删除用户、用户主动注销账号、GDPR 删除请求。
    业务路由的 DELETE 应改用软删，不要直接调用此函数。
    """
    if not user_ids:
        return {}
    placeholders = ",".join(["?"] * len(user_ids))
    db = get_db()
    counts: dict[str, int] = {}
    for tbl in _USER_DATA_TABLES + ("users",):
        try:
            cur = db.execute(
                f"DELETE FROM {tbl} WHERE user_id IN ({placeholders})"
                if tbl != "users"
                else f"DELETE FROM users WHERE id IN ({placeholders})",
                user_ids,
            )
            counts[tbl] = cur.rowcount
        except sqlite3.OperationalError:
            # 表可能在该环境下尚未通过迁移创建——忽略
            counts[tbl] = 0
    db.commit()
    return counts


def soft_delete(table: str, *, user_id: int, row_id: int) -> bool:
    """把指定用户的某条记录标记为已删除（不真正 DELETE）。返回是否命中。"""
    if table not in {"records", "income", "assets", "financial_goals"}:
        raise ValueError(f"软删未覆盖此表：{table}")
    db = get_db()
    cur = db.execute(
        f"UPDATE {table} SET deleted_at = ? "
        f"WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (datetime.utcnow().isoformat(timespec="seconds"), row_id, user_id),
    )
    db.commit()
    return cur.rowcount > 0

