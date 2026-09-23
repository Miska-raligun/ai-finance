-- 0002 智能体验：异常预警 / 自动归类缓存 / 月度报告 / 用户长期画像

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    period TEXT NOT NULL,                -- YYYY-MM
    format TEXT DEFAULT 'markdown',
    content TEXT,
    insights_json TEXT,
    created_at TEXT,
    UNIQUE(user_id, period)
);

CREATE INDEX IF NOT EXISTS idx_reports_user ON reports(user_id, created_at);

CREATE TABLE IF NOT EXISTS user_profile (
    user_id INTEGER PRIMARY KEY,
    facts_json TEXT,
    income_band TEXT,
    family_size INTEGER,
    mortgage REAL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS category_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    note_hash TEXT NOT NULL,
    note_sample TEXT,
    category TEXT NOT NULL,
    hits INTEGER DEFAULT 1,
    updated_at TEXT,
    UNIQUE(user_id, note_hash)
);

CREATE INDEX IF NOT EXISTS idx_catcache_user ON category_cache(user_id);

-- records 表追加异常评分列（runner 仅执行一次，不会重复 ALTER）
ALTER TABLE records ADD COLUMN anomaly_score REAL;
ALTER TABLE records ADD COLUMN anomaly_flag INTEGER DEFAULT 0;
