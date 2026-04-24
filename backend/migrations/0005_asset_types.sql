-- 0005 资产类型用户自管理
-- 1) 新增 asset_types 表（结构参考 categories）
-- 2) 根据现有 assets.type 为每个用户回填同名类型，并把英文 type 映射成中文名
-- 3) 拆掉 assets.type 的 CHECK 约束（SQLite 通过重建表实现）

CREATE TABLE IF NOT EXISTS asset_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    shape TEXT NOT NULL CHECK(shape IN ('security_auto','security_manual','lump','cash')),
    quote_source TEXT,
    created_at TEXT,
    UNIQUE(user_id, name)
);
CREATE INDEX IF NOT EXISTS idx_asset_types_user ON asset_types(user_id);

-- 为每个已存在的 (user_id, type) 补建一条 asset_types 行
INSERT OR IGNORE INTO asset_types (user_id, name, shape, quote_source, created_at)
SELECT DISTINCT user_id,
       CASE type
         WHEN 'stock'      THEN '股票'
         WHEN 'fund'       THEN '基金'
         WHEN 'bond'       THEN '债券'
         WHEN 'cash'       THEN '现金'
         WHEN 'crypto'     THEN '加密货币'
         WHEN 'realestate' THEN '房地产'
         WHEN 'other'      THEN '其他'
         ELSE type
       END AS name,
       CASE type
         WHEN 'stock'  THEN 'security_auto'
         WHEN 'fund'   THEN 'security_auto'
         WHEN 'crypto' THEN 'security_manual'
         WHEN 'cash'   THEN 'cash'
         ELSE 'lump'
       END AS shape,
       CASE type
         WHEN 'stock' THEN 'stock'
         WHEN 'fund'  THEN 'fund'
         ELSE NULL
       END AS quote_source,
       datetime('now')
  FROM assets;

-- 重建 assets 表以去掉 CHECK(type IN (...)) 约束
CREATE TABLE assets_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    symbol TEXT,
    holdings REAL DEFAULT 0,
    cost_basis REAL DEFAULT 0,
    current_value REAL DEFAULT 0,
    currency TEXT DEFAULT 'CNY',
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

-- 把英文 type 映射成中文迁移过来
INSERT INTO assets_new
  (id, user_id, name, type, symbol, holdings, cost_basis, current_value, currency, notes, created_at, updated_at)
SELECT id, user_id, name,
       CASE type
         WHEN 'stock'      THEN '股票'
         WHEN 'fund'       THEN '基金'
         WHEN 'bond'       THEN '债券'
         WHEN 'cash'       THEN '现金'
         WHEN 'crypto'     THEN '加密货币'
         WHEN 'realestate' THEN '房地产'
         WHEN 'other'      THEN '其他'
         ELSE type
       END,
       symbol, holdings, cost_basis, current_value, currency, notes, created_at, updated_at
  FROM assets;

DROP TABLE assets;
ALTER TABLE assets_new RENAME TO assets;

CREATE INDEX IF NOT EXISTS idx_assets_user ON assets(user_id);
CREATE INDEX IF NOT EXISTS idx_assets_user_type ON assets(user_id, type);

-- 之前 0004 建过的唯一约束需要重建
CREATE UNIQUE INDEX IF NOT EXISTS uniq_assets_user_name ON assets(user_id, name);
