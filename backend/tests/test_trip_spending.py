"""行程花费:记账和旅行计划之间那条线。

这个模块存在的理由就是 records.trip_id——没有它,旅行计划只是
一个碰巧住在记账 App 里的日历。所以重点测"归属"本身:
自动归、批量归、逐条改、以及**不该**归的那些情况。
"""
from __future__ import annotations


def _foreign_trip(app) -> int:
    """另一个用户名下的行程,用来测越权。"""
    from werkzeug.security import generate_password_hash
    from db import get_db
    with app.app_context():
        conn = get_db()
        conn.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, 0)",
                     ("other", generate_password_hash("pwd")))
        oid = conn.execute("SELECT id FROM users WHERE username = 'other'").fetchone()[0]
        conn.execute("INSERT INTO trips (user_id, title, start_date, end_date) "
                     "VALUES (?, '别人的行程', '2026-09-26', '2026-09-29')", (oid,))
        conn.commit()
        return conn.execute("SELECT id FROM trips WHERE user_id = ?", (oid,)).fetchone()[0]


def _mk_trip(client, **kw):
    payload = {"title": "北欧四国", "start_date": "2026-09-26",
               "end_date": "2026-09-29", "accent": "glacier"}
    payload.update(kw)
    return client.post("/api/trips", json=payload).get_json()["id"]


def _spend(client, date, amount=100, category="餐饮", note=""):
    r = client.post("/api/records", json={
        "category": category, "amount": amount, "note": note, "date": date})
    assert r.status_code in (200, 201), r.get_json()
    return r.get_json()


def _uid(app):
    from db import get_db
    with app.app_context():
        return get_db().execute(
            "SELECT id FROM users WHERE username = 'tester'").fetchone()[0]


def _earn(app, date, amount=100, category="退税", note=""):
    """收入目前只有 chat handler 这一条入口,没有 REST POST。"""
    from handlers.income import add_income
    from constants import PARAM_AMOUNT, PARAM_CATEGORY, PARAM_DATE, PARAM_NOTE
    with app.app_context():
        add_income(_uid(app), {PARAM_CATEGORY: category, PARAM_AMOUNT: amount,
                               PARAM_NOTE: note, PARAM_DATE: date})


def _trip_id_of(app, table, row_id):
    from db import get_db
    with app.app_context():
        return get_db().execute(
            f"SELECT trip_id FROM {table} WHERE id = ?", (row_id,)).fetchone()["trip_id"]


def _last_id(app, table):
    from db import get_db
    with app.app_context():
        return get_db().execute(f"SELECT MAX(id) FROM {table}").fetchone()[0]


# ---------- 新记一笔时自动归属 ----------

def test_record_in_trip_window_auto_attaches(app, auth_client):
    tid = _mk_trip(auth_client)
    _spend(auth_client, "2026-09-27", 240, "餐饮", "赫尔辛基晚饭")
    assert _trip_id_of(app, "records", _last_id(app, "records")) == tid


def test_record_outside_window_stays_free(app, auth_client):
    _mk_trip(auth_client)
    _spend(auth_client, "2026-10-05", 30)
    assert _trip_id_of(app, "records", _last_id(app, "records")) is None


def test_overlapping_trips_refuse_to_guess(app, auth_client):
    """两趟行程盖住同一天时不猜——猜错的归属比没归属更难发现。"""
    _mk_trip(auth_client)
    _mk_trip(auth_client, title="顺道去丹麦",
             start_date="2026-09-28", end_date="2026-10-02")
    _spend(auth_client, "2026-09-28", 88)
    assert _trip_id_of(app, "records", _last_id(app, "records")) is None


def test_deleted_trip_does_not_capture(app, auth_client):
    tid = _mk_trip(auth_client)
    assert auth_client.delete(f"/api/trips/{tid}").status_code == 200
    _spend(auth_client, "2026-09-27", 50)
    assert _trip_id_of(app, "records", _last_id(app, "records")) is None


def test_income_auto_attaches_too(app, auth_client):
    """退税/退款是真实存在的旅行收入,不跟着算净花费就是错的。"""
    tid = _mk_trip(auth_client)
    _earn(app, "2026-09-29", 300, "退税", "机场退税")
    assert _trip_id_of(app, "income", _last_id(app, "income")) == tid


# ---------- 汇总 ----------

def test_summary_totals_and_breakdown(app, auth_client):
    tid = _mk_trip(auth_client)
    _spend(auth_client, "2026-09-26", 100, "交通")
    _spend(auth_client, "2026-09-26", 50, "餐饮")
    _spend(auth_client, "2026-09-27", 200, "交通")
    _earn(app, "2026-09-29", 60)

    s = auth_client.get(f"/api/trips/{tid}/spending").get_json()
    assert s["total"] == 350
    assert s["refund"] == 60
    assert s["net"] == 290
    assert s["count"] == 4
    assert s["by_category"][0] == {"category": "交通", "amount": 300}
    assert s["by_day"] == [{"date": "2026-09-26", "amount": 150},
                           {"date": "2026-09-27", "amount": 200}]
    assert len(s["records"]) == 3 and len(s["income"]) == 1


def test_summary_skips_deleted_records(app, auth_client):
    tid = _mk_trip(auth_client)
    _spend(auth_client, "2026-09-26", 100)
    rid = _last_id(app, "records")
    _spend(auth_client, "2026-09-27", 40)
    assert auth_client.delete(f"/api/records/{rid}").status_code == 200

    s = auth_client.get(f"/api/trips/{tid}/spending").get_json()
    assert s["total"] == 40


def test_summary_refuses_other_users_trip(app, auth_client):
    foreign = _foreign_trip(app)
    assert auth_client.get(f"/api/trips/{foreign}/spending").status_code == 404
    assert auth_client.post(f"/api/trips/{foreign}/spending/attach",
                            json={}).status_code == 404
    assert auth_client.delete(f"/api/trips/{foreign}/spending/attach").status_code == 404


# ---------- 批量归入 / 解除 ----------

def test_attach_range_defaults_to_trip_dates(app, auth_client):
    """先有账再建行程是常态(机票早就买了),所以要能补归。"""
    _spend(auth_client, "2026-09-26", 100)
    _spend(auth_client, "2026-09-27", 100)
    _spend(auth_client, "2026-10-01", 100)          # 行程之外
    tid = _mk_trip(auth_client)

    r = auth_client.post(f"/api/trips/{tid}/spending/attach", json={})
    assert r.status_code == 200 and r.get_json()["moved"] == 2
    assert auth_client.get(f"/api/trips/{tid}/spending").get_json()["total"] == 200


def test_attach_range_does_not_steal_from_other_trip(app, auth_client):
    first = _mk_trip(auth_client)
    _spend(auth_client, "2026-09-27", 100)          # 自动归给 first
    second = _mk_trip(auth_client, title="第二趟",
                      start_date="2026-09-20", end_date="2026-10-10")

    auth_client.post(f"/api/trips/{second}/spending/attach", json={})
    assert auth_client.get(f"/api/trips/{first}/spending").get_json()["total"] == 100
    assert auth_client.get(f"/api/trips/{second}/spending").get_json()["total"] == 0


def test_attach_rejects_bad_range(app, auth_client):
    tid = _mk_trip(auth_client)
    assert auth_client.post(f"/api/trips/{tid}/spending/attach",
                            json={"start": "2026/09/26", "end": "2026-09-29"}).status_code == 400
    assert auth_client.post(f"/api/trips/{tid}/spending/attach",
                            json={"start": "2026-09-29", "end": "2026-09-26"}).status_code == 400


def test_detach_all_keeps_the_records(app, auth_client):
    tid = _mk_trip(auth_client)
    _spend(auth_client, "2026-09-27", 100)
    assert auth_client.delete(f"/api/trips/{tid}/spending/attach").get_json()["moved"] == 1
    assert auth_client.get(f"/api/trips/{tid}/spending").get_json()["total"] == 0
    # 账目本身还在账本里
    assert auth_client.get("/api/records").get_json()["total"] == 1


# ---------- 逐条改归属 ----------

def test_put_can_move_and_clear_trip(app, auth_client):
    tid = _mk_trip(auth_client)
    _spend(auth_client, "2026-10-20", 77)           # 行程外,未归属
    rid = _last_id(app, "records")

    r = auth_client.put(f"/api/records/{rid}", json={
        "category": "餐饮", "amount": 77, "note": "", "date": "2026-10-20", "trip_id": tid})
    assert r.status_code == 200
    assert _trip_id_of(app, "records", rid) == tid

    auth_client.put(f"/api/records/{rid}", json={
        "category": "餐饮", "amount": 77, "note": "", "date": "2026-10-20", "trip_id": None})
    assert _trip_id_of(app, "records", rid) is None


def test_put_without_trip_id_keeps_attribution(app, auth_client):
    """改个金额不该把记录从行程里踢出去。"""
    tid = _mk_trip(auth_client)
    _spend(auth_client, "2026-09-27", 100)
    rid = _last_id(app, "records")

    auth_client.put(f"/api/records/{rid}", json={
        "category": "餐饮", "amount": 120, "note": "改价", "date": "2026-09-27"})
    assert _trip_id_of(app, "records", rid) == tid


def test_put_rejects_foreign_trip(app, auth_client):
    """指向别人的行程只会变成查不出来的脏数据,宁可 400。"""
    foreign = _foreign_trip(app)
    _spend(auth_client, "2026-11-01", 10)
    rid = _last_id(app, "records")
    r = auth_client.put(f"/api/records/{rid}", json={
        "category": "餐饮", "amount": 10, "note": "", "date": "2026-11-01",
        "trip_id": foreign})
    assert r.status_code == 400
    assert _trip_id_of(app, "records", rid) is None


# ---------- 账本侧 ----------

def test_records_list_exposes_and_filters_trip(app, auth_client):
    tid = _mk_trip(auth_client)
    _spend(auth_client, "2026-09-27", 100)
    _spend(auth_client, "2026-10-20", 30)

    all_rows = auth_client.get("/api/records").get_json()["data"]
    assert {r["trip_id"] for r in all_rows} == {tid, None}

    mine = auth_client.get(f"/api/records?trip_id={tid}").get_json()
    assert mine["total"] == 1 and mine["sum_amount"] == 100

    free = auth_client.get("/api/records?trip_id=none").get_json()
    assert free["total"] == 1 and free["sum_amount"] == 30
