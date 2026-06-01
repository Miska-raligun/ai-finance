"""聚合 SQL 全链路过滤 deleted_at：recap / checkup / decide / stats 都不该把已软删的行算进来。"""
from datetime import datetime


def _seed(app, uid, period):
    from db import get_db
    with app.app_context():
        db = get_db()
        # 两条「活」记录 + 一条已被软删的记录（金额够大，能影响所有聚合）
        db.execute(
            "INSERT INTO records (user_id, category, amount, note, date) "
            "VALUES (?, '餐饮', 50, '', ?)", (uid, f"{period}-05"))
        db.execute(
            "INSERT INTO records (user_id, category, amount, note, date) "
            "VALUES (?, '购物', 200, '', ?)", (uid, f"{period}-10"))
        db.execute(
            "INSERT INTO records (user_id, category, amount, note, date, deleted_at) "
            "VALUES (?, '其它', 9999, '已删', ?, ?)",
            (uid, f"{period}-15", "2026-05-29T00:00:00"))
        db.execute(
            "INSERT INTO income (user_id, category, amount, note, date) "
            "VALUES (?, '工资', 3000, '', ?)", (uid, f"{period}-05"))
        db.execute(
            "INSERT INTO income (user_id, category, amount, note, date, deleted_at) "
            "VALUES (?, '加班', 5000, '已删', ?, ?)",
            (uid, f"{period}-06", "2026-05-29T00:00:00"))
        db.commit()


def test_recap_excludes_deleted(auth_client, app, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    period = datetime.now().strftime("%Y-%m")
    _seed(app, uid, period)

    body = auth_client.get(f"/api/reports/recap?month={period}").get_json()
    # 活记录：餐饮 50 + 购物 200 = 250。已删的 9999 不该出现在任何字段。
    assert body["spend_total"] == 250.0
    assert body["income_total"] == 3000.0
    assert body["largest_txn"]["amount"] == 200.0
    assert body["largest_txn"]["category"] == "购物"
    # 花最多的一天是 10 号（购物 200），不是 15 号（被删的 9999）
    assert body["highest_day"]["date"].endswith("-10")


def test_checkup_excludes_deleted(auth_client, app, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    period = datetime.now().strftime("%Y-%m")
    _seed(app, uid, period)

    body = auth_client.post(f"/api/checkup/compute?month={period}").get_json()
    ctx = body["context"]
    assert ctx["spend_total"] == 250.0
    assert ctx["income_total"] == 3000.0


def test_decide_excludes_deleted(auth_client, app, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    period = datetime.now().strftime("%Y-%m")
    _seed(app, uid, period)

    body = auth_client.post(
        "/api/decide", json={"item": "键盘", "price": 500}
    ).get_json()
    ctx = body["context_used"]
    # 月均支出按近 3 月算：本月只有 250 活记录 → 月均≈83，不该被 9999 拖到 ~3416
    assert ctx["spend_avg_monthly"] < 200
    assert ctx["month_spend"] == 250.0
    assert ctx["income_30d"] == 3000.0


def test_stats_excludes_deleted(auth_client, app):
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    period = datetime.now().strftime("%Y-%m")
    _seed(app, uid, period)

    cats = auth_client.get(f"/api/stats/by-category?month={period}").get_json()
    # 不该出现「其它 9999」这一类（被软删）
    names = [c["名称"] for c in cats]
    assert "其它" not in names
    assert "加班" not in names
    spend = sum(c["金额"] for c in cats if c["类型"] == "支出")
    income = sum(c["金额"] for c in cats if c["类型"] == "收入")
    assert spend == 250.0
    assert income == 3000.0

    summary = auth_client.get(f"/api/stats/summary?month={period}").get_json()
    assert summary["总支出"] == 250.0
    assert summary["总收入"] == 3000.0
