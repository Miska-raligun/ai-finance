"""支出异常检测：基于同分类近 90 天滚动 z-score。"""
from __future__ import annotations

import math
import statistics
from datetime import datetime, timedelta
from typing import Optional

from db import get_db

# 阈值：|z| 超过 ZSCORE_THRESHOLD 即标记异常
ZSCORE_THRESHOLD = 2.5
# 至少有 MIN_SAMPLES 条历史数据才计算（数据稀少时容易误报）
MIN_SAMPLES = 5
# 历史窗口（天）
WINDOW_DAYS = 90


def detect(user_id: int, category: str, amount: float, date: Optional[str] = None) -> dict:
    """返回 {"score": float|None, "flag": 0|1, "reason": str}。

    无足够数据或类别无意义时 score=None, flag=0。
    """
    if not category or amount <= 0:
        return {"score": None, "flag": 0, "reason": ""}

    today = datetime.now().date() if not date else datetime.strptime(date, "%Y-%m-%d").date()
    start = (today - timedelta(days=WINDOW_DAYS)).isoformat()

    rows = get_db().execute(
        "SELECT amount FROM records WHERE user_id = ? AND category = ? AND date >= ? AND date <= ?",
        (user_id, category, start, today.isoformat()),
    ).fetchall()
    samples = [float(r["amount"]) for r in rows if (r["amount"] or 0) > 0]
    if len(samples) < MIN_SAMPLES:
        return {"score": None, "flag": 0, "reason": ""}

    mean = statistics.fmean(samples)
    try:
        stdev = statistics.stdev(samples)
    except statistics.StatisticsError:
        stdev = 0.0
    if stdev <= 0:
        # 均值有效但方差为 0，按倍数判断
        if amount > mean * 3:
            return {"score": float("inf"), "flag": 1,
                    "reason": f"明显高于「{category}」近 {WINDOW_DAYS} 天均值（¥{mean:.2f}）"}
        return {"score": None, "flag": 0, "reason": ""}

    score = (amount - mean) / stdev
    if math.isnan(score):
        return {"score": None, "flag": 0, "reason": ""}

    flag = 1 if abs(score) >= ZSCORE_THRESHOLD else 0
    reason = ""
    if flag:
        direction = "高于" if score > 0 else "低于"
        reason = (
            f"该笔金额{direction}「{category}」近 {WINDOW_DAYS} 天均值 ¥{mean:.2f} "
            f"约 {abs(score):.1f} 个标准差，请确认是否输错。"
        )
    return {"score": round(score, 3), "flag": flag, "reason": reason}
