"""LLM 工具调用入口（handlers.invest_*）的单测。"""


def test_invest_add_asset_and_summary(app):
    from handlers import invest_add_asset, invest_portfolio_summary
    with app.app_context():
        msg = invest_add_asset(1, {
            "名称": "科技ETF", "类型": "fund",
            "数量": 500, "成本": 1000, "现值": 1200,
        })
        assert msg.startswith("✅")

        summary = invest_portfolio_summary(1)
        assert "科技ETF" in summary or "总市值" in summary
        assert "1200" in summary


def test_invest_update_value_unknown(app):
    from handlers import invest_update_value
    with app.app_context():
        msg = invest_update_value(1, {"名称": "不存在", "现值": 10})
        assert "未找到" in msg


def test_invest_add_goal_requires_target(app):
    from handlers import invest_add_goal
    with app.app_context():
        msg = invest_add_goal(1, {"名称": "留学基金"})
        assert msg.startswith("⚠️")


def test_invest_add_asset_rejects_bad_type(app):
    from handlers import invest_add_asset
    with app.app_context():
        msg = invest_add_asset(1, {"名称": "X", "类型": "bogus"})
        assert msg.startswith("⚠️")
