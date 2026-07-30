"""方案 A:投资盈亏(source='investment')排除出消费结构分析,但计入总收支。"""
from __future__ import annotations

from datetime import datetime


def _seed(app):
    from db import get_db
    with app.app_context():
        db = get_db()
        uid = db.execute("SELECT id FROM users WHERE username='tester'").fetchone()[0]
        month = datetime.now().strftime("%Y-%m")
        d = f"{month}-15"
        # 日常支出
        db.execute("INSERT INTO records (user_id,category,amount,note,date,source) "
                   "VALUES (?,?,?,?,?,NULL)", (uid, "餐饮", 100, "午饭", d))
        # 投资亏损(卖出结算写入)
        db.execute("INSERT INTO records (user_id,category,amount,note,date,source) "
                   "VALUES (?,?,?,?,?, 'investment')", (uid, "投资亏损", 500, "卖出A", d))
        # 日常收入 + 投资盈利
        db.execute("INSERT INTO income (user_id,category,amount,note,date,source) "
                   "VALUES (?,?,?,?,?,NULL)", (uid, "工资", 8000, "月薪", d))
        db.execute("INSERT INTO income (user_id,category,amount,note,date,source) "
                   "VALUES (?,?,?,?,?, 'investment')", (uid, "投资盈利", 300, "卖出B", d))
        db.commit()
        return uid, month


def test_category_breakdown_excludes_investment(app, auth_client):
    _seed(app)
    rows = auth_client.get("/api/stats/by-category").get_json()
    names = [r["名称"] for r in rows]
    assert "餐饮" in names
    assert "工资" in names
    # 投资盈亏不进消费/收入结构饼图
    assert "投资亏损" not in names
    assert "投资盈利" not in names


def test_summary_still_includes_investment(app, auth_client):
    _, month = _seed(app)
    s = auth_client.get(f"/api/stats/summary?month={month}").get_json()
    # 总支出 = 100 餐饮 + 500 投资亏损(计入总收支,保留对净现金流的影响)
    assert s["总支出"] == 600.0
    assert s["总收入"] == 8300.0
    assert s["结余"] == 7700.0


def test_calendar_excludes_investment(app, auth_client):
    _, month = _seed(app)
    data = auth_client.get("/api/stats/calendar?days=90").get_json()["data"]
    day = f"{month}-15"
    row = next((r for r in data if r["date"] == day), None)
    assert row is not None
    # 日历那天的 expense 只算日常 100,不含 500 投资亏损
    assert row["expense"] == 100.0
    assert row["income"] == 8000.0
