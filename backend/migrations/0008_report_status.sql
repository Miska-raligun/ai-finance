-- 0008_report_status.sql：把月报生成改为异步任务的支撑列。
--
-- 流程：
--   1. POST /api/reports/generate 立刻插入一行 status='pending'，启动后台线程后返回
--   2. 后台线程把 status 切到 'running' → 调 LLM → 成功改 'done' + content；
--      失败改 'failed' + error_message
--   3. 前端轮询 GET /api/reports/<period>/status 直到 done/failed
--
-- 旧版同步生成的行 (无 status 列) 视为已完成，所以默认值 'done'。

ALTER TABLE reports ADD COLUMN status TEXT DEFAULT 'done';
ALTER TABLE reports ADD COLUMN error_message TEXT;
ALTER TABLE reports ADD COLUMN updated_at TEXT;

-- 状态查询索引
CREATE INDEX IF NOT EXISTS idx_reports_user_status ON reports(user_id, status);
