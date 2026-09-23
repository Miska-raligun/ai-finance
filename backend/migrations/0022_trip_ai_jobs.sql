-- 0022 行程 AI 生成作业。
--
--  一次 LLM 调用做不出一份完整行程,所以拆成「骨架 + 逐天细化」多步跑。
--  多步就需要一张表:
--    * 每步的成败单独记,失败只重跑那一天,不用整趟重来
--    * 前端轮询看进度(和月报那套异步生成一个思路)
--    * 进程重启后能把卡住的 running 收尸,不然前端会一直转圈
--
--  steps_json 形如 [{"key":"day-3","label":"第 3 天","status":"done","error":null}]
CREATE TABLE IF NOT EXISTS trip_ai_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    trip_id INTEGER,                      -- 骨架跑完才有
    kind TEXT NOT NULL,                   -- import_notice | from_idea | fill_days
    status TEXT NOT NULL DEFAULT 'pending', -- pending|running|done|failed|cancelled
    input_json TEXT,
    steps_json TEXT,
    done INTEGER DEFAULT 0,
    total INTEGER DEFAULT 0,
    error TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_trip_ai_jobs_user ON trip_ai_jobs(user_id, id DESC);
