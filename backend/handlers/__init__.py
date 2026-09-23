"""按业务域拆分的 LLM 工具调用 handler 集合。

历史上 handlers 是单文件 871 行，承载支出/收入/预算/分类/查询/投资 等多块逻辑。
拆分后保持 `from handlers import add_record` 等历史导入路径不变（依赖包级
re-export）。新代码请按业务域 import 子模块（例如 `from handlers.budgets import ...`）。
"""
from __future__ import annotations

import logging

# 所有调用此 logger 的子模块共享同一份 file handler，避免重复打开句柄。
_llm_logger = logging.getLogger("llm_budget_suggest")
_llm_logger.setLevel(logging.INFO)
if not _llm_logger.handlers:
    _h = logging.FileHandler("llm_budget_suggest.log", encoding="utf-8")
    _h.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    _llm_logger.addHandler(_h)


# 显式 re-export：tools.py 仍执行 `from handlers import add_record, ...`
from .records import add_record, search_records, delete_record, category_sum  # noqa: E402,F401
from .income import add_income, query_income, delete_income  # noqa: E402,F401
from .budgets import (  # noqa: E402,F401
    set_budget, update_budget, delete_budget, budget_remain,
    suggest_budgets, call_deepseek_budget_advice,
)
from .categories import add_category, delete_category  # noqa: E402,F401
from .analysis import analyze_spend  # noqa: E402,F401
from .investment import (  # noqa: E402,F401
    invest_add_asset, invest_update_value, invest_add_goal,
    invest_portfolio_summary, invest_analyze_portfolio, invest_refresh_prices,
)

__all__ = [
    "add_record", "search_records", "delete_record", "category_sum",
    "add_income", "query_income", "delete_income",
    "set_budget", "update_budget", "delete_budget", "budget_remain",
    "suggest_budgets", "call_deepseek_budget_advice",
    "add_category", "delete_category",
    "analyze_spend",
    "invest_add_asset", "invest_update_value", "invest_add_goal",
    "invest_portfolio_summary", "invest_analyze_portfolio", "invest_refresh_prices",
]
