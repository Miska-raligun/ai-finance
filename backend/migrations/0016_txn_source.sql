-- 0016 记账来源标记:区分「日常收支」与「投资盈亏结算」。
--
-- 卖出/归档资产的浮盈浮亏会写进 income/records,但那不是消费/收入行为——
-- 以前会污染消费结构饼图、异常检测、预算已花。加 source 后:
--   source IS NULL / 'manual'  → 日常收支(参与消费分析、预算、异常)
--   source = 'investment'      → 投资盈亏(只计入净收支总额,排除出消费分析)
ALTER TABLE records ADD COLUMN source TEXT;
ALTER TABLE income ADD COLUMN source TEXT;

CREATE INDEX IF NOT EXISTS idx_records_user_source ON records(user_id, source);
CREATE INDEX IF NOT EXISTS idx_income_user_source ON income(user_id, source);
