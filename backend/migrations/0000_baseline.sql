-- 0000 基线迁移：与 db.py:init_db() 中的初始 schema 保持一致。
-- 全部使用 IF NOT EXISTS，对已有数据库幂等无副作用。
-- 仅作为新数据库的统一入口，遗留 ALTER 仍由 init_db() 处理。

CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    category TEXT,
    amount REAL,
    note TEXT,
    date TEXT
);

CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    category TEXT,
    amount REAL,
    cycle TEXT DEFAULT 'monthly',
    month TEXT,
    UNIQUE(category, month, user_id)
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT,
    type TEXT CHECK(type IN ('支出', '收入')) DEFAULT '支出',
    UNIQUE(name, user_id)
);

CREATE TABLE IF NOT EXISTS income (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    category TEXT,
    amount REAL,
    note TEXT,
    date TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    is_admin INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS llm_config (
    user_id INTEGER PRIMARY KEY,
    url TEXT,
    apikey TEXT,
    model TEXT,
    persona TEXT
);

CREATE TABLE IF NOT EXISTS chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    role TEXT,
    content TEXT
);

CREATE INDEX IF NOT EXISTS idx_records_user_date ON records(user_id, date);
CREATE INDEX IF NOT EXISTS idx_records_user_cat ON records(user_id, category);
CREATE INDEX IF NOT EXISTS idx_income_user_date ON income(user_id, date);
CREATE INDEX IF NOT EXISTS idx_income_user_cat ON income(user_id, category);
CREATE INDEX IF NOT EXISTS idx_budgets_user_month ON budgets(user_id, month);
CREATE INDEX IF NOT EXISTS idx_budgets_user_month_cat ON budgets(user_id, month, category);
