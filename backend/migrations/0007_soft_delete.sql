-- 0007_soft_delete.sql：为高频删除的业务表加软删字段，便于审计与误删恢复。
-- SQLite 不支持 IF NOT EXISTS 给 ALTER TABLE，所以走 CREATE INDEX 时同时
-- 把列也补上；列由迁移脚本前置的 ALTER 处理（runner 会按文件顺序逐条 exec）。

-- records
ALTER TABLE records ADD COLUMN deleted_at TEXT;
CREATE INDEX IF NOT EXISTS idx_records_user_alive
    ON records(user_id, date) WHERE deleted_at IS NULL;

-- income
ALTER TABLE income ADD COLUMN deleted_at TEXT;
CREATE INDEX IF NOT EXISTS idx_income_user_alive
    ON income(user_id, date) WHERE deleted_at IS NULL;

-- assets
ALTER TABLE assets ADD COLUMN deleted_at TEXT;
CREATE INDEX IF NOT EXISTS idx_assets_user_alive
    ON assets(user_id) WHERE deleted_at IS NULL;

-- financial_goals
ALTER TABLE financial_goals ADD COLUMN deleted_at TEXT;

-- LLM 用量看板：补 (created_at) 索引，避免 admin 看板大表全扫
CREATE INDEX IF NOT EXISTS idx_llm_usage_created ON llm_usage(created_at);
CREATE INDEX IF NOT EXISTS idx_llm_usage_user_day ON llm_usage(user_id, created_at);
