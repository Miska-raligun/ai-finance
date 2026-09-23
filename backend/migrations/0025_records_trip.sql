-- 0025 账本条目归属到行程。
--
--  这是「旅行计划」留在记账 App 里的理由:出门那几天花的钱,回来能算清
--  这趟一共花了多少、哪天最贵。没有这一列,旅行模块只是和账本共用一个
--  部署的另一个应用,两边一行数据都不相干。
--
--  支出和收入都加:退税、退款是旅行里真实存在的回流(行程单的速查里就写着
--  三个退税节点),只算支出会把这趟的实际成本算高。
--
--  可空:绝大多数记账和旅行无关。软删的行程不清这一列——恢复行程时归属还在。
ALTER TABLE records ADD COLUMN trip_id INTEGER;
ALTER TABLE income ADD COLUMN trip_id INTEGER;

CREATE INDEX IF NOT EXISTS idx_records_trip ON records(trip_id, date);
CREATE INDEX IF NOT EXISTS idx_income_trip ON income(trip_id, date);
