-- 0010_llm_usage_observability.sql：扩展 llm_usage 观测维度。
--
-- 旧版仅记 token；admin 看板只能算"花了多少额度"，看不到失败率和延迟。
-- 新列：
--   latency_ms     请求耗时（ms）。失败请求也会记，用于绘制 P95 / P99 曲线。
--   status         'success' | 'error' | 'quota_exceeded' | 'timeout'
--   error_reason   失败时填错误消息前 200 字符；成功时 NULL
--   provider       openai / anthropic / gemini，便于按厂商分组对比
-- cost_usd 字段已经存在但一直恒为 0，本次开始由 services/llm_pricing.py 估算填入。
ALTER TABLE llm_usage ADD COLUMN latency_ms INTEGER;
ALTER TABLE llm_usage ADD COLUMN status TEXT;
ALTER TABLE llm_usage ADD COLUMN error_reason TEXT;
ALTER TABLE llm_usage ADD COLUMN provider TEXT;

-- 按 status 查"今日失败率"或"调用了多少次成功"
CREATE INDEX IF NOT EXISTS idx_llm_usage_status ON llm_usage(status, created_at);
