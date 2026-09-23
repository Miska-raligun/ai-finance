-- 0020 速查信息:领队电话、使馆电话、航班、时差、货币、硬规定等。
--
--  * body 存**纯文本**(保留换行),不存 HTML——公开分享页会渲染它,
--    存 HTML 等于给自己开一个 XSS 口子。前端按 pre-wrap 展示,
--    并把电话号码识别成可拨链接。
--  * is_public 逐条控制是否出现在公开分享页,默认 0(不公开)。
--    领队手机号这类是第三方个人信息,默认外泄不可接受;要分享给同行的人
--    再逐条打开。
CREATE TABLE IF NOT EXISTS trip_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    body TEXT,
    is_public INTEGER DEFAULT 0,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_trip_facts_trip ON trip_facts(trip_id, sort_order);
