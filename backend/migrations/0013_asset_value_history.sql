-- 0013_asset_value_history.sql：资产市值历史快照。
--
-- 用于 AssetTable 抽屉里画小折线图，回看持仓的市值走势。
-- 每次 refresh_user_assets 写一条；可视化时按 asset_id 拉最近 N 天聚合。
CREATE TABLE IF NOT EXISTS asset_value_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    asset_id INTEGER NOT NULL,
    value REAL NOT NULL,           -- 总市值快照（current_value）
    recorded_at TEXT NOT NULL      -- ISO 'YYYY-MM-DDTHH:MM:SS'
);

-- 高频查询：按 asset_id + 时间倒序
CREATE INDEX IF NOT EXISTS idx_asset_value_history_asset_time
    ON asset_value_history(asset_id, recorded_at DESC);
-- 清理时按 user_id 批量
CREATE INDEX IF NOT EXISTS idx_asset_value_history_user
    ON asset_value_history(user_id);
