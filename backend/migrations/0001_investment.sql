-- 0001 投资模块：资产、交易流水、目标、风险测评
-- 设计原则：
--   * 不依赖实时行情，current_value 由用户/AI 录入
--   * asset_transactions 用于估算回报率（XIRR 简化版）
--   * financial_goals 跟踪长期理财目标进度

CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('stock','fund','bond','cash','crypto','realestate','other')),
    symbol TEXT,
    holdings REAL DEFAULT 0,
    cost_basis REAL DEFAULT 0,
    current_value REAL DEFAULT 0,
    currency TEXT DEFAULT 'CNY',
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_assets_user ON assets(user_id);
CREATE INDEX IF NOT EXISTS idx_assets_user_type ON assets(user_id, type);

CREATE TABLE IF NOT EXISTS asset_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    asset_id INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('buy','sell','dividend','adjust')),
    quantity REAL DEFAULT 0,
    price REAL DEFAULT 0,
    fee REAL DEFAULT 0,
    date TEXT NOT NULL,
    note TEXT,
    created_at TEXT,
    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_atx_user_date ON asset_transactions(user_id, date);
CREATE INDEX IF NOT EXISTS idx_atx_asset ON asset_transactions(asset_id);

CREATE TABLE IF NOT EXISTS financial_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    target_amount REAL NOT NULL,
    deadline TEXT,
    current_progress REAL DEFAULT 0,
    priority INTEGER DEFAULT 3,
    note TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_goals_user ON financial_goals(user_id);

CREATE TABLE IF NOT EXISTS risk_profiles (
    user_id INTEGER PRIMARY KEY,
    level TEXT,
    score INTEGER,
    answers_json TEXT,
    summary TEXT,
    updated_at TEXT
);
