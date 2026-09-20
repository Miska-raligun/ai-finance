-- 0019 行程分享:生成一个公开只读链接,外人凭 token 查看行程。
--
-- 安全约定(公开端点只读这张表定位 trip,字段白名单在 routes/travel.py):
--   * token 用 secrets.token_urlsafe(16) 生成,不可枚举
--   * revoked_at 非空即失效;行程被软删后公开端点同样 404
--   * 手记(trip_days.journal)与打包清单永不出现在公开响应里
CREATE TABLE IF NOT EXISTS trip_shares (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    token TEXT NOT NULL UNIQUE,
    created_at TEXT,
    revoked_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_trip_shares_trip ON trip_shares(trip_id, revoked_at);
