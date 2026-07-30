"""定期账单 / 重复记账规则的展开。

设计：
  * 每条规则有 day_of_month (1-31)。月不足 31 天时（如 2 月 30 日），把
    规则展开到当月最后一天。
  * last_run_date 防重：同一个月份内重复触发不会写第二笔。
  * 展开时复用 handlers.add_record / add_income，保证分类自动创建、异常检测
    与 cache 失效 等一致行为。

调度入口：scripts/run_recurring.py，由 cron 或 systemd timer 调用。
"""
from __future__ import annotations

import calendar
import logging
from datetime import date as _date
from typing import Any

from constants import PARAM_AMOUNT, PARAM_CATEGORY, PARAM_DATE, PARAM_NOTE
from db import get_db

logger = logging.getLogger(__name__)


def _resolve_day(target: _date, day_of_month: int) -> _date:
    """day_of_month 超出当月天数时回退到月末。"""
    last_day = calendar.monthrange(target.year, target.month)[1]
    d = min(day_of_month, last_day)
    return _date(target.year, target.month, d)


def list_due_rules(conn, on_date: _date, user_id: int | None = None) -> list[dict]:
    """返回当月所有应执行但还没执行的规则。

    应执行 = active=1 AND _resolve_day(on_date, day_of_month) <= on_date
    未执行 = last_run_date 不在 on_date 的当月
    user_id 传入时只扫该用户(前台手动触发用);None 为全量(cron 用)。
    """
    sql = ("SELECT id, user_id, kind, category, amount, day_of_month, note, "
           "last_run_date FROM recurring_rules WHERE active = 1")
    args: list = []
    if user_id is not None:
        sql += " AND user_id = ?"
        args.append(user_id)
    rows = conn.execute(sql, args).fetchall()
    due = []
    cur_month_prefix = on_date.strftime("%Y-%m")
    for r in rows:
        scheduled = _resolve_day(on_date, int(r["day_of_month"]))
        if scheduled > on_date:
            continue  # 本月还没到日子
        last = r["last_run_date"] or ""
        if last.startswith(cur_month_prefix):
            continue  # 当月已跑过
        due.append({**dict(r), "scheduled_date": scheduled.isoformat()})
    return due


def run_due(on_date: _date | None = None, user_id: int | None = None) -> dict:
    """展开到期规则，返回 {executed, skipped, errors}。

    `on_date` 默认今天。`user_id` 传入时只展开该用户的规则(前台「立即执行」用,
    避免一个用户触发全站展开);None 为全量(后台 cron 用)。
    展开操作通过 handlers 走完整的"添加一笔记账"链路,保证一致性
    (自动建分类 / 缓存失效 / 异常检测)。
    """
    on_date = on_date or _date.today()
    db = get_db()
    due = list_due_rules(db, on_date, user_id=user_id)
    if not due:
        return {"executed": 0, "skipped": 0, "errors": [], "as_of": on_date.isoformat()}

    # 后台调用 handlers 时需要把 user_id 当参数传，handler 自身不依赖 Flask g
    from handlers import add_record, add_income

    executed, errors = 0, []
    for rule in due:
        try:
            params = {
                PARAM_CATEGORY: rule["category"],
                PARAM_AMOUNT: float(rule["amount"]),
                PARAM_NOTE: f"[定期] {rule['note'] or ''}".rstrip(),
                PARAM_DATE: rule["scheduled_date"],
            }
            handler = add_income if rule["kind"] == "income" else add_record
            result = handler(int(rule["user_id"]), params)
            if not result.startswith("✅"):
                errors.append({"rule_id": rule["id"], "reason": result})
                continue
            db.execute(
                "UPDATE recurring_rules SET last_run_date = ?, updated_at = datetime('now') "
                "WHERE id = ?",
                (rule["scheduled_date"], rule["id"]),
            )
            executed += 1
        except Exception as e:  # noqa: BLE001
            logger.exception("recurring rule id=%s failed", rule["id"])
            errors.append({"rule_id": rule["id"], "reason": str(e)})

    db.commit()
    return {
        "executed": executed,
        "skipped": len(due) - executed - len(errors),
        "errors": errors,
        "as_of": on_date.isoformat(),
    }
