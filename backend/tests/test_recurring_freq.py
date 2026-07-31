"""定期账单多频率:weekly / yearly 的到期判定 + 当期去重。"""
from __future__ import annotations

from datetime import date

from services.recurring import _rule_due, _scheduled_date


def _rule(**kw):
    base = {"freq": "monthly", "day_of_month": 1, "day_of_week": None,
            "month_of_year": None, "last_run_date": ""}
    base.update(kw)
    return base


def test_monthly_backward_compatible():
    r = _rule(freq="monthly", day_of_month=15)
    assert _rule_due(r, date(2026, 7, 15)) is True
    assert _rule_due(r, date(2026, 7, 14)) is False          # 还没到日子
    r2 = _rule(freq="monthly", day_of_month=15, last_run_date="2026-07-15")
    assert _rule_due(r2, date(2026, 7, 20)) is False         # 当月已跑


def test_monthly_month_end_fallback():
    r = _rule(freq="monthly", day_of_month=31)
    # 2 月没有 31 号 → 回退到 2/28(2026 非闰年)
    assert _rule_due(r, date(2026, 2, 28)) is True
    assert _scheduled_date(r, date(2026, 2, 28)) == date(2026, 2, 28)


def test_weekly():
    # 2026-07-15 是周三(weekday()=2)
    r = _rule(freq="weekly", day_of_week=2)
    assert _rule_due(r, date(2026, 7, 15)) is True
    assert _rule_due(r, date(2026, 7, 16)) is False          # 周四,非指定
    # 本周已跑过(周一之后)→ 不再触发
    r2 = _rule(freq="weekly", day_of_week=2, last_run_date="2026-07-15")
    assert _rule_due(r2, date(2026, 7, 15)) is False
    # 下周三应再次触发
    assert _rule_due(r2, date(2026, 7, 22)) is True


def test_yearly():
    r = _rule(freq="yearly", month_of_year=3, day_of_month=10)
    assert _rule_due(r, date(2026, 3, 10)) is True
    assert _rule_due(r, date(2026, 3, 9)) is False
    assert _rule_due(r, date(2026, 4, 1)) is True            # 过了 3/10,当年还没跑
    r2 = _rule(freq="yearly", month_of_year=3, day_of_month=10, last_run_date="2026-03-10")
    assert _rule_due(r2, date(2026, 6, 1)) is False          # 当年已跑
    assert _rule_due(r2, date(2027, 3, 10)) is True          # 次年再触发


def test_create_weekly_rule_via_api(app, auth_client):
    r = auth_client.post("/api/recurring", json={
        "kind": "expense", "category": "订阅", "amount": 15,
        "freq": "weekly", "day_of_week": 0, "note": "周报会员",
    })
    assert r.status_code == 201
    rules = auth_client.get("/api/recurring").get_json()
    wk = [x for x in rules if x["freq"] == "weekly"]
    assert wk and wk[0]["day_of_week"] == 0
