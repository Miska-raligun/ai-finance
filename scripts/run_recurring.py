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
import fcntl
import json
import os
import sqlite3
import sys
from datetime import datetime, date as _date

# 把 backend/ 加进 sys.path
HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "backend"))
sys.path.insert(0, BACKEND)

LOCK_PATH = "/tmp/ai-finance-recurring.lock"
HISTORY_RETENTION_DAYS = int(os.getenv("ASSET_HISTORY_RETENTION_DAYS", "90"))


def _acquire_lock():
    """非阻塞 flock：cron 与 systemd timer 重叠时第二份立即退出，杜绝重复展开。

    持有的文件对象必须返回给调用方，函数返回即释放锁。
    """
    f = open(LOCK_PATH, "w")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"⚠️ 另一个 run_recurring 进程在跑（锁：{LOCK_PATH}），本次跳过",
              file=sys.stderr)
        f.close()
        return None
    return f


def _cleanup_old_asset_history(db_file: str) -> int:
    """清理 asset_value_history 超过 N 天的快照，避免高频写入表无限膨胀。

    保留 90 天足够 AssetTable 抽屉里画历史折线。

    清理结束后顺手做一次 WAL checkpoint(TRUNCATE):WAL 模式下 -wal 文件会持续
    增长,只在 checkpoint 时收缩;每天 cron 跑一次刚好。
    """
    conn = sqlite3.connect(db_file)
    try:
        cur = conn.execute(
            "DELETE FROM asset_value_history WHERE recorded_at < datetime('now', ?)",
            (f"-{HISTORY_RETENTION_DAYS} days",),
        )
        conn.commit()
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            pass
        return cur.rowcount or 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="展开定期记账规则 + 清理资产历史快照")
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

    lock = _acquire_lock()
    if lock is None:
        return 0

    try:
        # 触发迁移（若 0011 / 0013 还没跑过，会在这里追上）
        import db as _db
        _db.init_db()

        from services.recurring import run_due
        result = run_due(on_date=on)

        # 顺手清理 asset_value_history 旧快照（90 天前的）。失败不阻断主流程。
        try:
            n = _cleanup_old_asset_history(_db.DB_FILE)
            result["asset_history_cleaned"] = n
            if n:
                print(f"🧹 清理 asset_value_history 旧快照 {n} 行")
        except sqlite3.Error as e:
            print(f"⚠️ 清理 asset_value_history 失败：{e}", file=sys.stderr)
            result["asset_history_cleaned"] = None

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if not result["errors"] else 1
    finally:
        # 显式释放锁文件
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        lock.close()


if __name__ == "__main__":
    sys.exit(main())
