-- 0015 体检 / 回顾结果缓存:避免每次接口调用都重跑 LLM。
--
-- checkup_scores 加 context_json 字段:把 _gather() 算出来的画像也存下来,
-- 命中缓存时直接还原,不必重做聚合查询。
ALTER TABLE checkup_scores ADD COLUMN context_json TEXT;

-- recap_cache:本月回顾卡片的命中缓存,结构上回顾结果是个嵌套 dict,
-- 直接 JSON 落盘最省事。force=True 时 upsert 覆盖。
CREATE TABLE IF NOT EXISTS recap_cache (
    user_id INTEGER NOT NULL,
    period TEXT NOT NULL,
    highlights_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, period)
);
