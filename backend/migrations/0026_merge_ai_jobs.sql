-- 0026 把 trip_ai_jobs 并进 ai_jobs:一张表、一个线程池、一个状态端点。
--
--  这两张表是分两次长出来的:先有多步的行程生成(0022/0023),后来财务体检
--  和购前决策也要异步,又开了一张(0024)。结果是同一件事有两套实现——
--  两个 ThreadPoolExecutor(各自的并发上限互不知情,加起来能同时打 5 个
--  LLM)、两套收尸逻辑、两个轮询端点,前端也就有了两个轮询工具。
--
--  单步作业只是"步骤数为 1"的多步作业,没有必要分家。这里给 ai_jobs 补上
--  多步需要的几列,把旧行搬过来,然后把旧表删掉。
--
--  注意:搬过来的行会拿到新的自增 id。in-flight 的作业本来就活不过重启
--  (启动时一律收尸成 failed),前端拿旧 id 轮询会得到 404 并提示重试,
--  这是可以接受的;换 id 换来的是不用在一张表里塞两套 id 空间。
ALTER TABLE ai_jobs ADD COLUMN trip_id INTEGER;
ALTER TABLE ai_jobs ADD COLUMN steps_json TEXT;
ALTER TABLE ai_jobs ADD COLUMN done INTEGER DEFAULT 0;
ALTER TABLE ai_jobs ADD COLUMN total INTEGER DEFAULT 0;

INSERT INTO ai_jobs (user_id, kind, dedup_key, status, input_json, result_json,
                     error, created_at, updated_at, trip_id, steps_json, done, total)
SELECT user_id, kind, NULL, status, input_json, result_json,
       error, created_at, updated_at, trip_id, steps_json, done, total
FROM trip_ai_jobs;

DROP TABLE trip_ai_jobs;

CREATE INDEX IF NOT EXISTS idx_ai_jobs_trip ON ai_jobs(trip_id, id DESC);
