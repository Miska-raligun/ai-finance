"""定期账单：CRUD + 展开逻辑。"""
from datetime import date as _date


def _seed_rule(app, uid, *, kind="expense", category="房租", amount=3000,
               day=1, note="11月房租"):
    from db import get_db
    with app.app_context():
        db = get_db()
        cur = db.execute(
            "INSERT INTO recurring_rules "
            "(user_id, kind, category, amount, day_of_month, note, active, "
            " created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, datetime('now'), datetime('now'))",
            (uid, kind, category, amount, day, note),
        )
        db.commit()
        return cur.lastrowid


# ---- CRUD ----

def test_create_rule_validates_fields(auth_client):
    r = auth_client.post("/api/recurring", json={"kind": "weird"})
    assert r.status_code == 400

    r = auth_client.post("/api/recurring",
                         json={"kind": "expense", "category": "", "amount": 100, "day_of_month": 1})
    assert r.status_code == 400

    r = auth_client.post("/api/recurring",
                         json={"kind": "expense", "category": "x", "amount": -5, "day_of_month": 1})
    assert r.status_code == 400

    r = auth_client.post("/api/recurring",
                         json={"kind": "expense", "category": "x", "amount": 1, "day_of_month": 32})
    assert r.status_code == 400


def test_full_crud_cycle(auth_client):
    r = auth_client.post("/api/recurring", json={
        "kind": "expense", "category": "房租", "amount": 3000,
        "day_of_month": 1, "note": "月租金",
    })
    assert r.status_code == 201
    rid = r.get_json()["id"]

    r = auth_client.get("/api/recurring")
    assert r.status_code == 200
    body = r.get_json()
    assert any(x["id"] == rid for x in body)

    r = auth_client.patch(f"/api/recurring/{rid}", json={"amount": 3500, "active": False})
    assert r.status_code == 200

    r = auth_client.get("/api/recurring")
    rule = next(x for x in r.get_json() if x["id"] == rid)
    assert rule["amount"] == 3500
    assert rule["active"] == 0

    r = auth_client.delete(f"/api/recurring/{rid}")
    assert r.status_code == 200
    r = auth_client.delete(f"/api/recurring/{rid}")
    assert r.status_code == 404


# ---- 展开逻辑 ----

def test_run_due_creates_record(auth_client, app):
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    _seed_rule(app, uid, day=1, amount=3000, category="房租")

    with app.app_context():
        from services.recurring import run_due
        result = run_due(on_date=_date(2025, 4, 1))
        assert result["executed"] == 1

        from db import get_db
        row = get_db().execute(
            "SELECT category, amount, note, date FROM records WHERE user_id = ?",
            (uid,)
        ).fetchone()
        assert row is not None
        assert row["category"] == "房租"
        assert abs(row["amount"] - 3000) < 0.01
        assert row["date"] == "2025-04-01"
        assert "[定期]" in row["note"]


def test_run_due_idempotent_same_month(auth_client, app):
    """同一月内重复跑不会写第二笔记录。"""
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    _seed_rule(app, uid, day=1)

    with app.app_context():
        from services.recurring import run_due
        run_due(on_date=_date(2025, 4, 1))
        run_due(on_date=_date(2025, 4, 15))  # 同月再跑

        from db import get_db
        cnt = get_db().execute(
            "SELECT COUNT(*) FROM records WHERE user_id = ?", (uid,)
        ).fetchone()[0]
        assert cnt == 1


def test_run_due_clamps_day_to_month_end(auth_client, app):
    """day_of_month=31 在 2 月被回退到 28/29 号。"""
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    _seed_rule(app, uid, day=31, category="保险")

    with app.app_context():
        from services.recurring import run_due
        run_due(on_date=_date(2025, 2, 28))  # 2025 非闰年
        from db import get_db
        row = get_db().execute(
            "SELECT date FROM records WHERE user_id = ?", (uid,)
        ).fetchone()
        assert row["date"] == "2025-02-28"


def test_run_due_skips_future_day(auth_client, app):
    """当月还没到日子的规则不展开。"""
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    _seed_rule(app, uid, day=20)

    with app.app_context():
        from services.recurring import run_due
        result = run_due(on_date=_date(2025, 4, 5))
        assert result["executed"] == 0


def test_run_due_income_kind(auth_client, app):
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    _seed_rule(app, uid, kind="income", category="工资", amount=10000, day=5)

    with app.app_context():
        from services.recurring import run_due
        run_due(on_date=_date(2025, 4, 10))
        from db import get_db
        rec = get_db().execute(
            "SELECT category, amount FROM income WHERE user_id = ?", (uid,)
        ).fetchone()
        assert rec is not None
        assert rec["category"] == "工资"
        assert abs(rec["amount"] - 10000) < 0.01
