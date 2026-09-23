"""共用的轻量输入校验。"""
from __future__ import annotations

from datetime import datetime


def is_month(value) -> bool:
    """是不是合法的 YYYY-MM。

    不能只判长度:"2025/04" 同样是 7 个字符,照样会被放行。
    """
    if not isinstance(value, str) or len(value) != 7:
        return False
    try:
        datetime.strptime(value, "%Y-%m")
    except ValueError:
        return False
    return True
