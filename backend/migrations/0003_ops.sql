-- 0003 运维基础：LLM 用量追踪 + Captcha 持久化
-- 注：版本号 0001/0002 预留给后续 Sprint（投资模块、智能体验）

CREATE TABLE IF NOT EXISTS llm_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    endpoint TEXT,
    model TEXT,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    request_id TEXT,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_user_date ON llm_usage(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_llm_usage_endpoint ON llm_usage(endpoint);

CREATE TABLE IF NOT EXISTS captcha_store (
    token TEXT PRIMARY KEY,
    answer TEXT NOT NULL,
    expires_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_captcha_expires ON captcha_store(expires_at);
