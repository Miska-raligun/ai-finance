"""验证 handlers 拆分后符号 / 路由分发表完全保留。"""


def test_top_level_imports_still_work(temp_db):
    """tools.py 等历史代码靠 `from handlers import add_record` 直接 import。"""
    from handlers import (
        add_record, add_income, set_budget, update_budget, analyze_spend,
        add_category, delete_category, budget_remain, delete_budget,
        suggest_budgets, query_income, category_sum, search_records,
        delete_record, delete_income,
        invest_add_asset, invest_update_value, invest_add_goal,
        invest_portfolio_summary, invest_analyze_portfolio, invest_refresh_prices,
    )
    # 都必须是可调用对象，不能是 None / 字符串
    for fn in [add_record, add_income, set_budget, analyze_spend,
               invest_add_asset, invest_portfolio_summary]:
        assert callable(fn)


def test_submodule_imports(temp_db):
    """新代码可以按业务域 import，避免顶层包重新加载所有模块。"""
    from handlers.records import add_record as ar_records
    from handlers.income import add_income as ai_income
    from handlers.budgets import set_budget as sb_budgets
    from handlers.investment import invest_add_asset as iaa_invest
    from handlers import add_record as ar_pkg

    # 同一函数对象，不能因 re-export 出现两份
    assert ar_records is ar_pkg
    assert callable(ai_income)
    assert callable(sb_budgets)
    assert callable(iaa_invest)


def test_dispatch_table_full(temp_db):
    """LLM 工具 dispatch（tools.handlers）必须把 22 个旧名称全部映射到可调用对象。"""
    from tools import handlers as dispatch
    expected = {
        "add_record", "add_income", "set_budget", "update_budget",
        "analyze_spend", "add_category", "delete_category",
        "budget_remain", "delete_budget", "suggest_budgets",
        "query_income", "category_sum", "search_records",
        "delete_record", "delete_income",
        "invest_add_asset", "invest_update_value", "invest_add_goal",
        "invest_portfolio_summary", "invest_analyze_portfolio", "invest_refresh_prices",
    }
    missing = expected - set(dispatch)
    assert not missing, f"dispatch 表遗漏：{missing}"
    for k, v in dispatch.items():
        assert callable(v), f"{k} 不是可调用对象"


def test_add_record_round_trip(auth_client):
    """端到端冒烟：经 dispatch 调用 add_record，库里能查到。"""
    from db import get_db
    from flask import g
    from tools import handlers as dispatch

    # auth_client fixture 下走 app context；构造一个最小 g
    with auth_client.application.app_context():
        # 模拟当前登录用户（从 session_transaction 读不到 g.user_id，
        # 直接用 fixture 已经把 user_id 写进 session 的方式拿）
        with auth_client.session_transaction() as s:
            uid = s["user_id"]
        result = dispatch["add_record"](uid, {"分类": "餐饮", "金额": 12.5, "备注": "午餐"})
        assert "✅" in result
        row = get_db().execute(
            "SELECT category, amount FROM records WHERE user_id = ?", (uid,),
        ).fetchone()
        assert row is not None
        assert row["category"] == "餐饮"
        assert float(row["amount"]) == 12.5
