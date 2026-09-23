-- 0014 财务体检：保存每月健康分 + 四维拆解 + AI 报告，供趋势线复用。
CREATE TABLE IF NOT EXISTS checkup_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    period TEXT NOT NULL,              -- YYYY-MM
    score INTEGER NOT NULL,            -- 0-100
    dimensions_json TEXT,              -- [{name, score, max, comment}]
    report TEXT,                       -- AI 体检报告（纯文本）
    source TEXT DEFAULT 'llm',         -- llm / fallback
    created_at TEXT,
    UNIQUE(user_id, period)
);

CREATE INDEX IF NOT EXISTS idx_checkup_user ON checkup_scores(user_id, period);
