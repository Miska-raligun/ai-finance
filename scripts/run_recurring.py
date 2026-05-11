#!/usr/bin/env python3
"""定期账单 / 重复记账 cron 入口。

每日 00:05 执行（或任意时间），扫所有 active 规则，把"今天到期且当月还没
跑过"的规则展开成 records / income 行。

用法：
    scripts/run_recurring.py                # 用今天的日期
    scripts/run_recurring.py --date=2025-05-01  # 指定日期（补单用）

crontab 推荐：
    5 0 * * *  cd /path/to/ai-finance/backend && \
        ../scripts/run_recurring.py >> ../logs/recurring.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, date as _date

# 把 backend/ 加进 sys.path
HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "backend"))
sys.path.insert(0, BACKEND)


def main() -> int:
    parser = argparse.ArgumentParser(description="展开定期记账规则")
    parser.add_argument("--date", help="指定执行日期 YYYY-MM-DD，默认今天")
    args = parser.parse_args()

    if args.date:
        try:
            on = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print(f"❌ 日期格式应为 YYYY-MM-DD：{args.date}", file=sys.stderr)
            return 2
    else:
        on = _date.today()

    # 触发迁移（若 0011 还没跑过，会在这里追上）
    import db as _db
    _db.init_db()

    from services.recurring import run_due
    result = run_due(on_date=on)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
