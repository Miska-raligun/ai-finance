-- 0004 投资模块加固：
--   1. 同一用户下 assets.name 必须唯一（先清洗历史重名再加索引）
--   2. 新增 quote_cache 表，缓存股票/基金行情 10 分钟

UPDATE assets
   SET name = name || ' (dup-' || id || ')'
 WHERE id NOT IN (SELECT MIN(id) FROM assets GROUP BY user_id, name);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_assets_user_name ON assets(user_id, name);

CREATE TABLE IF NOT EXISTS quote_cache (
    symbol TEXT PRIMARY KEY,
    asset_type TEXT,
    price REAL NOT NULL,
    name TEXT,
    currency TEXT,
    fetched_at INTEGER NOT NULL
);
