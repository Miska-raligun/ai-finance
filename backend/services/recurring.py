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


def _rule_due(r: dict, on_date: _date) -> bool:
    """按频率判断规则在 on_date 是否「到期且当期未跑过」。

    monthly: 当月到日 且 last_run 不在当月
    weekly : on_date 是指定星期几 且 last_run 早于本周一(ISO 周)
    yearly : 到达当年的 月/日 且 last_run 不在当年
    """
    freq = (r.get("freq") or "monthly").lower()
    last = r.get("last_run_date") or ""

    if freq == "weekly":
        dow = r.get("day_of_week")
        if dow is None or on_date.weekday() != int(dow):
            return False
        week_start = on_date.fromordinal(on_date.toordinal() - on_date.weekday())
        return not last or last < week_start.isoformat()

    if freq == "yearly":
        moy = int(r.get("month_of_year") or 1)
        last_day = calendar.monthrange(on_date.year, moy)[1]
        scheduled = _date(on_date.year, moy, min(int(r["day_of_month"] or 1), last_day))
        if scheduled > on_date:
            return False
        return not last.startswith(str(on_date.year))

    # monthly(默认)
    scheduled = _resolve_day(on_date, int(r["day_of_month"] or 1))
    if scheduled > on_date:
        return False
    return not last.startswith(on_date.strftime("%Y-%m"))


def _scheduled_date(r: dict, on_date: _date) -> _date:
    """规则本期应记账的日期(展开时写进 records/income 的 date)。"""
    freq = (r.get("freq") or "monthly").lower()
    if freq == "weekly":
        return on_date  # 就是今天(命中的那个星期几)
    if freq == "yearly":
        moy = int(r.get("month_of_year") or 1)
        last_day = calendar.monthrange(on_date.year, moy)[1]
        return _date(on_date.year, moy, min(int(r["day_of_month"] or 1), last_day))
    return _resolve_day(on_date, int(r["day_of_month"] or 1))


def list_due_rules(conn, on_date: _date, user_id: int | None = None) -> list[dict]:
    """返回到期且当期未执行的规则(按 freq 判定,见 _rule_due)。
    user_id 传入时只扫该用户(前台手动触发用);None 为全量(cron 用)。
    """
    sql = ("SELECT id, user_id, kind, category, amount, day_of_month, note, "
           "last_run_date, freq, day_of_week, month_of_year "
           "FROM recurring_rules WHERE active = 1")
    args: list = []
    if user_id is not None:
        sql += " AND user_id = ?"
        args.append(user_id)
    rows = conn.execute(sql, args).fetchall()
    due = []
    for row in rows:
        r = dict(row)
        if _rule_due(r, on_date):
            due.append({**r, "scheduled_date": _scheduled_date(r, on_date).isoformat()})
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
