-- 0011_recurring_rules.sql：定期账单 / 重复记账规则表。
--
-- 用户填一条"每月 1 日房租 ¥3000"，cron 跑 scripts/run_recurring.py 会自动
-- 把它当天 due 的规则展开成 records / income 行，并更新 last_run_date 防重。
CREATE TABLE IF NOT EXISTS recurring_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('expense', 'income')),
    category TEXT NOT NULL,
    amount REAL NOT NULL,
    day_of_month INTEGER NOT NULL CHECK(day_of_month BETWEEN 1 AND 31),
    note TEXT,
    active INTEGER NOT NULL DEFAULT 1,           -- 0 = 暂停
    last_run_date TEXT,                          -- ISO 'YYYY-MM-DD'，防同月重复执行
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_recurring_user_active
    ON recurring_rules(user_id, active);
