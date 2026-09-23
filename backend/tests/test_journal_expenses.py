"""从手记里记账:提取是草稿,逐条确认才入账。

这条链路把"旅行计划"和"记账"真正接上了:以前手记只是一段死文本,
写在里面的花费不会变成账。
"""
from __future__ import annotations

import json
import time


def _mk_trip(client, **kw):
    payload = {"title": "北欧四国", "start_date": "2026-10-01", "end_date": "2026-10-05"}
    payload.update(kw)
    return client.post("/api/trips", json=payload).get_json()["id"]


def _wait(client, job_id, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/ai-jobs/{job_id}").get_json()
        if job["status"] in ("done", "failed", "cancelled"):
            return job
        time.sleep(0.03)
    raise AssertionError("任务超时")


def _stub(monkeypatch, items):
    seen = {}

    def fake(messages, llm=None, tools=None, tool_choice=None,
             temperature=0.3, timeout=10, endpoint="unknown"):
        seen["endpoint"] = endpoint
        seen["user"] = messages[-1]["content"]
        return {"choices": [{"message": {"content": json.dumps(
            {"items": items}, ensure_ascii=False)}}]}

    monkeypatch.setattr("services.llm._call_llm", fake)
    return seen


def _extract(client, tid, day_no=2):
    r = client.post(f"/api/trips/{tid}/ai/block",
                    json={"kind": "journal_expenses", "day_no": day_no})
    assert r.status_code == 201, r.get_json()
    return _wait(client, r.get_json()["job_id"])


# ---------- 提取 ----------

def test_extracts_candidates_from_the_journal(app, auth_client, monkeypatch):
    seen = _stub(monkeypatch, [
        {"i": 1, "note": "午饭 烤肉", "amount": 240, "currency": "SEK",
         "category": "餐饮", "kind": "expense", "date": "2026-10-02", "sure": 1},
        {"i": 2, "note": "机场退税", "amount": 300, "currency": "SEK",
         "category": "退税", "kind": "income", "date": "2026-10-02", "sure": 1},
    ])
    tid = _mk_trip(auth_client)
    auth_client.patch(f"/api/trips/{tid}/days/2",
                      json={"journal": "中午吃了烤肉 240 克朗,走的时候退税拿回 300。"})

    job = _extract(auth_client, tid)
    assert job["status"] == "done"
    items = job["result"]["items"]
    assert [x["note"] for x in items] == ["午饭 烤肉", "机场退税"]
    assert items[0]["kind"] == "expense" and items[1]["kind"] == "income"
    # 手记原文是后端自己从库里取的,不由前端传
    assert "烤肉 240 克朗" in seen["user"]


def test_extraction_writes_nothing(app, auth_client, monkeypatch):
    """核心约束:抽出来的是候选,一分钱都不能自动进账本。"""
    _stub(monkeypatch, [{"i": 1, "note": "午饭", "amount": 240, "currency": "CNY",
                         "category": "餐饮", "kind": "expense", "date": "2026-10-02",
                         "sure": 1}])
    tid = _mk_trip(auth_client)
    auth_client.patch(f"/api/trips/{tid}/days/2", json={"journal": "午饭 240"})
    _extract(auth_client, tid)
    assert auth_client.get("/api/records").get_json()["total"] == 0


def test_garbage_amounts_are_dropped(app, auth_client, monkeypatch):
    _stub(monkeypatch, [
        {"note": "没金额"},
        {"note": "零", "amount": 0},
        {"note": "负的", "amount": -5},
        {"note": "天文数字", "amount": 9e9},
        {"note": "正常", "amount": 88, "currency": "CNY", "category": "餐饮",
         "date": "2026-10-02"},
    ])
    tid = _mk_trip(auth_client)
    auth_client.patch(f"/api/trips/{tid}/days/2", json={"journal": "x"})
    items = _extract(auth_client, tid)["result"]["items"]
    assert [x["note"] for x in items] == ["正常"]


def test_unknown_currency_stays_blank(app, auth_client, monkeypatch):
    """判断不出币种就留空,由用户来选。默认成人民币会把 240 克朗记成 240 块,
    而且从账本上看不出错。"""
    _stub(monkeypatch, [
        {"note": "a", "amount": 240, "currency": "克朗", "category": "餐饮",
         "date": "2026-10-02"},
        {"note": "b", "amount": 100, "currency": None, "category": "餐饮",
         "date": "2026-10-02"},
    ])
    tid = _mk_trip(auth_client)
    auth_client.patch(f"/api/trips/{tid}/days/2", json={"journal": "x"})
    items = _extract(auth_client, tid)["result"]["items"]
    assert all(x["currency"] == "" for x in items)


def test_bad_date_falls_back_to_the_day(app, auth_client, monkeypatch):
    _stub(monkeypatch, [{"note": "a", "amount": 50, "currency": "CNY",
                         "category": "餐饮", "date": "十月二号"}])
    tid = _mk_trip(auth_client)
    auth_client.patch(f"/api/trips/{tid}/days/2", json={"journal": "x"})
    items = _extract(auth_client, tid)["result"]["items"]
    assert items[0]["date"] == "2026-10-02"


def test_duplicate_is_flagged_not_blocked(app, auth_client, monkeypatch):
    """同一笔很可能聊天里已经记过了。只提醒不拦截——
    一天吃两顿一样贵的饭完全正常。"""
    tid = _mk_trip(auth_client)
    auth_client.post("/api/records", json={
        "category": "餐饮", "amount": 240, "note": "午饭", "date": "2026-10-02"})

    _stub(monkeypatch, [
        {"note": "午饭", "amount": 240, "currency": "CNY", "category": "餐饮",
         "date": "2026-10-02"},
        {"note": "晚饭", "amount": 99, "currency": "CNY", "category": "餐饮",
         "date": "2026-10-02"},
    ])
    auth_client.patch(f"/api/trips/{tid}/days/2", json={"journal": "x"})
    items = _extract(auth_client, tid)["result"]["items"]
    assert items[0]["dup"] == 1 and items[1]["dup"] == 0


def test_duplicate_check_uses_the_converted_amount(app, auth_client, monkeypatch):
    """账本里存的是人民币。拿 165 克朗去比 112.2 元永远比不上,
    查重就等于没有——外币那条路上最容易记重,偏偏最容易漏掉。"""
    monkeypatch.setattr("services.quotes.get_fx_to_cny", lambda c: 0.68)
    tid = _mk_trip(auth_client)
    auth_client.post("/api/records", json={
        "category": "交通", "amount": 112.2, "note": "地铁票", "date": "2026-10-02"})

    _stub(monkeypatch, [
        {"note": "地铁一日票", "amount": 165, "currency": "SEK", "category": "交通",
         "date": "2026-10-02"},
        {"note": "别的", "amount": 240, "currency": "SEK", "category": "餐饮",
         "date": "2026-10-02"},
    ])
    auth_client.patch(f"/api/trips/{tid}/days/2", json={"journal": "x"})
    items = _extract(auth_client, tid)["result"]["items"]
    assert items[0]["dup"] == 1          # 165 × 0.68 = 112.2,记过了
    assert items[1]["dup"] == 0


def test_foreign_amounts_carry_a_rate(app, auth_client, monkeypatch):
    """账本只存一个数字,没有币种列。所以外币要带一个汇率过去当默认值,
    折算后的金额由用户确认。"""
    monkeypatch.setattr("services.quotes.get_fx_to_cny", lambda c: 0.68)
    _stub(monkeypatch, [
        {"note": "午饭", "amount": 240, "currency": "SEK", "category": "餐饮",
         "date": "2026-10-02"},
        {"note": "打车", "amount": 30, "currency": "CNY", "category": "交通",
         "date": "2026-10-02"},
    ])
    tid = _mk_trip(auth_client)
    auth_client.patch(f"/api/trips/{tid}/days/2", json={"journal": "x"})
    items = _extract(auth_client, tid)["result"]["items"]
    assert items[0]["fx"] == 0.68
    assert "fx" not in items[1]          # 人民币不需要


def test_empty_journal_gives_nothing(app, auth_client, monkeypatch):
    _stub(monkeypatch, [{"note": "凭空捏造", "amount": 100}])
    tid = _mk_trip(auth_client)
    job = _extract(auth_client, tid)
    assert job["result"]["items"] == []   # 压根没调模型


def test_needs_a_day(app, auth_client, monkeypatch):
    _stub(monkeypatch, [])
    tid = _mk_trip(auth_client)
    assert auth_client.post(f"/api/trips/{tid}/ai/block",
                            json={"kind": "journal_expenses"}).status_code == 400


# ---------- 确认入账 ----------

def test_confirmed_items_land_in_the_ledger_on_this_trip(app, auth_client):
    tid = _mk_trip(auth_client)
    r = auth_client.post(f"/api/trips/{tid}/journal/records", json={"items": [
        {"note": "午饭 烤肉(240 SEK)", "amount": 163.2, "category": "餐饮",
         "date": "2026-10-02", "kind": "expense"},
        {"note": "机场退税", "amount": 204, "category": "退税",
         "date": "2026-10-02", "kind": "income"},
    ]})
    assert r.status_code == 200
    assert r.get_json() == {"created": 2, "errors": []}

    s = auth_client.get(f"/api/trips/{tid}/spending").get_json()
    assert s["total"] == 163.2 and s["refund"] == 204
    assert s["records"][0]["note"] == "午饭 烤肉(240 SEK)"


def test_committed_records_belong_to_the_trip_even_off_range(app, auth_client):
    """用户当面认过这笔是这趟的,就按这趟算——哪怕日期落在行程之外
    (回来才结的账、出发前买的票都是这种)。"""
    tid = _mk_trip(auth_client)
    auth_client.post(f"/api/trips/{tid}/journal/records", json={"items": [
        {"note": "回国后补的账", "amount": 99, "category": "购物",
         "date": "2026-11-20", "kind": "expense"},
    ]})
    assert auth_client.get(f"/api/trips/{tid}/spending").get_json()["total"] == 99


def test_bad_rows_are_reported_and_the_rest_still_land(app, auth_client):
    tid = _mk_trip(auth_client)
    r = auth_client.post(f"/api/trips/{tid}/journal/records", json={"items": [
        {"note": "好的", "amount": 50, "category": "餐饮", "date": "2026-10-02"},
        {"note": "金额不是数字", "amount": "abc", "category": "餐饮", "date": "2026-10-02"},
        {"note": "日期不对", "amount": 50, "category": "餐饮", "date": "2026/10/02"},
        {"note": "没分类", "amount": 50, "category": "", "date": "2026-10-02"},
    ]})
    body = r.get_json()
    assert body["created"] == 1
    assert [e["i"] for e in body["errors"]] == [1, 2, 3]
    assert auth_client.get(f"/api/trips/{tid}/spending").get_json()["total"] == 50


def test_commit_rejects_empty_and_oversized(app, auth_client):
    tid = _mk_trip(auth_client)
    assert auth_client.post(f"/api/trips/{tid}/journal/records",
                            json={"items": []}).status_code == 400
    many = [{"note": "x", "amount": 1, "category": "餐饮", "date": "2026-10-02"}] * 51
    assert auth_client.post(f"/api/trips/{tid}/journal/records",
                            json={"items": many}).status_code == 400


def test_commit_is_scoped_to_the_owner(app, auth_client):
    from werkzeug.security import generate_password_hash
    from db import get_db
    with auth_client.application.app_context():
        conn = get_db()
        conn.execute("INSERT INTO users (username, password) VALUES ('other', ?)",
                     (generate_password_hash("p"),))
        oid = conn.execute("SELECT id FROM users WHERE username='other'").fetchone()[0]
        conn.execute("INSERT INTO trips (user_id, title, start_date, end_date) "
                     "VALUES (?, '别人的', '2026-10-01', '2026-10-05')", (oid,))
        conn.commit()
        foreign = conn.execute("SELECT id FROM trips WHERE user_id = ?", (oid,)).fetchone()[0]

    assert auth_client.post(f"/api/trips/{foreign}/journal/records", json={"items": [
        {"note": "x", "amount": 1, "category": "餐饮", "date": "2026-10-02"}]}).status_code == 404


def test_duplicate_check_covers_income_too(app, auth_client, monkeypatch):
    """退税、退款很可能已经在聊天里记过一次了,查重不能只看支出那张表。

    反过来也不能串:同一天有一笔 300 的**收入**,不该把一笔 300 的支出
    也标成重复。
    """
    from handlers.income import add_income
    from constants import PARAM_AMOUNT, PARAM_CATEGORY, PARAM_DATE, PARAM_NOTE

    tid = _mk_trip(auth_client)
    with app.app_context():
        from db import get_db
        uid = get_db().execute("SELECT id FROM users WHERE username='tester'").fetchone()[0]
        add_income(uid, {PARAM_CATEGORY: "退税", PARAM_AMOUNT: 300,
                         PARAM_NOTE: "机场", PARAM_DATE: "2026-10-02"})

    _stub(monkeypatch, [
        {"note": "机场退税", "amount": 300, "currency": "CNY", "category": "退税",
         "kind": "income", "date": "2026-10-02"},
        {"note": "买了个包", "amount": 300, "currency": "CNY", "category": "购物",
         "kind": "expense", "date": "2026-10-02"},
    ])
    auth_client.patch(f"/api/trips/{tid}/days/2", json={"journal": "x"})
    items = _extract(auth_client, tid)["result"]["items"]
    assert items[0]["dup"] == 1          # 收入那笔记过了
    assert items[1]["dup"] == 0          # 支出没记过,不该被收入那笔带累
