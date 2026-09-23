"""投资模块 REST 路由：原 routes/investment.py 拆分为子模块。

为了不影响前端（路径全部保留 /api/investment/...）和 app.py 注册逻辑
（仍 `from routes.investment import investment_bp`），所有子模块共享一个
Blueprint 实例 `investment_bp`，由 _common.py 提供。
"""
from ._common import investment_bp

# 副作用导入：把每个子模块上的路由装饰器执行，注册到共享 bp。
from . import asset_types  # noqa: F401
from . import assets  # noqa: F401
from . import transactions  # noqa: F401
from . import portfolio  # noqa: F401
from . import goals  # noqa: F401
from . import risk  # noqa: F401
from . import advisor  # noqa: F401
from . import commit_pending  # noqa: F401

__all__ = ["investment_bp"]
