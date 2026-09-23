-- 0012_receipts.sql：收据 / 发票图片归档。
--
-- 用户上传账单图片走 OCR 后图片就丢，无法回查。这里：
--   * 按 sha256 去重（同一张图多次上传共享一个 receipt 行）
--   * 文件落到 backend/uploads/receipts/<sha256>.<ext>，DB 只存元信息
--   * record_id NULL 表示已上传但还没确认入账（用户取消了）
--     —— 后续可以做定期清理
CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    record_id INTEGER,         -- 关联到 records / income 表（任意一边）
    record_kind TEXT,          -- 'expense' / 'income'，便于反查
    mime TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    path TEXT NOT NULL,        -- 相对 backend/ 的路径
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_receipts_user ON receipts(user_id);
-- sha256 用作 dedup key，需要按用户去重（避免别人看到别人的图）
CREATE UNIQUE INDEX IF NOT EXISTS idx_receipts_user_sha
    ON receipts(user_id, sha256);
