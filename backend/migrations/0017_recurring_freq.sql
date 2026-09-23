-- 0017 定期账单支持多种频率(此前只有「每月某日」)。
--   freq='monthly' → 用 day_of_month(每月;不足则月末)
--   freq='weekly'  → 用 day_of_week(0=周一 .. 6=周日),每周该天
--   freq='yearly'  → 用 month_of_year + day_of_month,每年该月该日
-- 老数据 freq 默认 'monthly',行为不变。
ALTER TABLE recurring_rules ADD COLUMN freq TEXT DEFAULT 'monthly';
ALTER TABLE recurring_rules ADD COLUMN day_of_week INTEGER;    -- 0..6, weekly 用
ALTER TABLE recurring_rules ADD COLUMN month_of_year INTEGER;  -- 1..12, yearly 用
