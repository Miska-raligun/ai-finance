"""handlers 子模块共享工具。"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any  # noqa: F401  (子模块沿用)

logger = logging.getLogger("handlers")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def cur_month() -> str:
    return datetime.now().strftime("%Y-%m")


def prev_month_of(month: str) -> str:
    """'2025-04' → '2025-03'；处理跨年。"""
    yr, mon = int(month[:4]), int(month[5:7])
    return f"{yr - 1}-12" if mon == 1 else f"{yr}-{mon - 1:02d}"
