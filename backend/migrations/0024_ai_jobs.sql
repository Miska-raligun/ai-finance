-- 0024 通用的单次 AI 作业。
--
--  财务体检、买之前问一下这类要跑一大段 LLM 的端点,原来是同步 HTTP:
--  请求挂着等几分钟。这会同时踩三个坑——nginx 的 proxy_read_timeout、
--  nginx 连续超时后把上游熔断(表现就是莫名其妙的 503)、以及 waitress
--  默认只有 4 个工作线程被长请求占满。
--
--  和 trip_ai_jobs 分开:那张表是多步作业,要记每步的成败和进度;
--  这里是单次调用,只需要一个结果。
--
--  dedup_key:同一个用户对同一个目标(比如同一个月的体检)只排一个,
--  连点几下不会打出去几份 LLM 调用。
CREATE TABLE IF NOT EXISTS ai_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    dedup_key TEXT,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending|running|done|failed
    input_json TEXT,
    result_json TEXT,
    error TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_ai_jobs_user ON ai_jobs(user_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_ai_jobs_dedup ON ai_jobs(dedup_key, status);
