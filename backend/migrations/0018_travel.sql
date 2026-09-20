-- 0018 旅行计划模块:行程本(trips)+ 每日安排(trip_days)+ 打包清单(trip_pack_items)。
--
-- 设计要点:
--  * 一趟旅行 = 1 条 trips + N 条 trip_days,按日历展示、点进某天看详情。
--  * accent 是「每趟旅行自己的主题色」,前端把它注入成 CSS 变量作用域,
--    让不同行程有辨识度,同时外壳仍是应用统一风格。
--  * trip_days.detail_json 放当天的结构化明细(时间轴/景点/贴士/住宿/地图点等)。
--    这些字段数量多、形状会演进,拆成列会频繁迁移;整体读写、不需要按字段查询,
--    所以用 JSON 列。需要统计的字段(日期/路线)才单独建列。
--  * journal 是用户自己写的当日手记——原静态页存在 localStorage(换设备即丢),
--    这里入库,跟着账号多端同步。
--  * 软删除对齐 records/income 的既有约定。
CREATE TABLE IF NOT EXISTS trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,              -- 「逃离地球计划」
    subtitle TEXT,                    -- 「北欧四国 · 冰岛四晚」
    code TEXT,                        -- 团号 / 自定义编号
    start_date TEXT NOT NULL,         -- YYYY-MM-DD
    end_date TEXT NOT NULL,
    accent TEXT DEFAULT 'glacier',    -- 主题色预设名(glacier/aurora/ember/sakura/...)
    cover_note TEXT,                  -- hero 副文案
    created_at TEXT,
    updated_at TEXT,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS trip_days (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    day_no INTEGER NOT NULL,          -- 第几天(1 起)
    date TEXT NOT NULL,               -- YYYY-MM-DD,日历定位用
    route TEXT,                       -- 「赫尔辛基 → 塔林」
    transport TEXT,                   -- 航班/船班备注
    meal TEXT,                        -- 含餐:早/午/晚
    detail_json TEXT,                 -- {sched,spots,todo,cam,buy,warn,stay,stops}
    journal TEXT,                     -- 用户手记(多端同步)
    created_at TEXT,
    updated_at TEXT,
    UNIQUE(trip_id, day_no)
);

CREATE TABLE IF NOT EXISTS trip_pack_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    grp TEXT,                         -- 分组:证件/衣物/电子...
    label TEXT NOT NULL,
    hint TEXT,
    checked INTEGER DEFAULT 0,
    sort_order INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_trips_user ON trips(user_id, start_date DESC);
CREATE INDEX IF NOT EXISTS idx_trip_days_trip ON trip_days(trip_id, day_no);
CREATE INDEX IF NOT EXISTS idx_trip_days_user_date ON trip_days(user_id, date);
CREATE INDEX IF NOT EXISTS idx_trip_pack_trip ON trip_pack_items(trip_id, sort_order);
