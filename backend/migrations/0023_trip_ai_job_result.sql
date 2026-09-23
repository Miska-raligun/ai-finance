-- 0023 作业结果。
--
--  单块生成(景点介绍、当天贴士、打包、速查)原来是同步 HTTP:请求要一直挂着
--  等 LLM,慢的时候好几分钟。这会同时踩三个坑——nginx 的 proxy_read_timeout、
--  nginx 连续超时后把上游熔断(表现为莫名其妙的 503)、以及 waitress 默认
--  只有 4 个工作线程被长请求占满。
--
--  改成异步之后请求一秒内返回,结果放这一列,前端轮询取。
ALTER TABLE trip_ai_jobs ADD COLUMN result_json TEXT;
