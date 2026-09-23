"""核心 handlers 单测：add_record / add_income / set_budget / 预算预警。"""
from constants import PARAM_AMOUNT, PARAM_CATEGORY, PARAM_DATE, PARAM_NOTE


def test_add_record_creates_category(app):
    from handlers import add_record
    from db import get_db

    with app.app_context():
        msg = add_record(1, {
            PARAM_CATEGORY: "餐饮",
            PARAM_AMOUNT: 30,
            PARAM_NOTE: "午餐",
            PARAM_DATE: "2025-04-01",
        })
        assert msg.startswith("✅"), msg
        cat = get_db().execute(
            "SELECT type FROM categories WHERE name=? AND user_id=?",
            ("餐饮", 1),
        ).fetchone()
        assert cat is not None
        assert cat["type"] == "支出"


def test_add_record_blocks_income_category(app):
    from handlers import add_income, add_record

    with app.app_context():
        add_income(1, {PARAM_CATEGORY: "工资", PARAM_AMOUNT: 5000, PARAM_DATE: "2025-04-01"})
        msg = add_record(1, {PARAM_CATEGORY: "工资", PARAM_AMOUNT: 100, PARAM_DATE: "2025-04-01"})
        assert "不能作为支出" in msg


def test_budget_warning_at_80_percent(app):
    from handlers import add_record, set_budget

    with app.app_context():
        set_budget(1, {PARAM_CATEGORY: "餐饮", PARAM_AMOUNT: 100})
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        msg = add_record(1, {PARAM_CATEGORY: "餐饮", PARAM_AMOUNT: 85, PARAM_DATE: today})
        assert "预算已用" in msg or "已超预算" in msg


def test_budget_overage_warning(app):
    from handlers import add_record, set_budget

    with app.app_context():
        set_budget(1, {PARAM_CATEGORY: "购物", PARAM_AMOUNT: 50})
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        msg = add_record(1, {PARAM_CATEGORY: "购物", PARAM_AMOUNT: 80, PARAM_DATE: today})
        assert "已超预算" in msg
