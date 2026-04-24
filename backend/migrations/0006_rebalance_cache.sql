-- 0006 再平衡缓存：把 LLM 生成的目标配比存一段时间，避免每次刷新都走 LLM
CREATE TABLE IF NOT EXISTS rebalance_cache (
    user_id INTEGER NOT NULL,
    allocation_sig TEXT NOT NULL,   -- by_type 的稳定 hash
    risk_level TEXT,                 -- 可为 NULL（未测评）
    targets_json TEXT NOT NULL,      -- {"<类型>": <pct>, ...}
    rationale TEXT,
    created_at INTEGER NOT NULL,     -- epoch seconds
    PRIMARY KEY (user_id, allocation_sig, risk_level)
);
