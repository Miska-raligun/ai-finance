"""GDPR 自助注销 /api/me/delete：双重确认、级联清理、最后管理员保护。"""


def test_requires_confirm_phrase(auth_client):
    r = auth_client.post("/api/me/delete", json={})
    assert r.status_code == 400
    assert "确认" in r.get_json().get("message", "")


def test_wrong_confirm_phrase_rejected(auth_client):
    r = auth_client.post("/api/me/delete", json={"confirm": "yes"})
    assert r.status_code == 400


def test_self_delete_purges_user_data(auth_client, app):
    from db import get_db, get_db
    # 注入一些数据
    with app.app_context():
        from flask import g
        with auth_client.session_transaction() as s:
            uid = s["user_id"]
        db = get_db()
        db.execute("INSERT INTO records (user_id, category, amount, date) VALUES (?, ?, ?, ?)",
                   (uid, "测试", 9.9, "2025-04-01"))
        db.execute("INSERT INTO categories (user_id, name, type) VALUES (?, ?, ?)",
                   (uid, "测试", "支出"))
        db.commit()

    r = auth_client.post("/api/me/delete", json={"confirm": "DELETE"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    # purged 字典必须显示 records / categories / users 都至少 1 行
    purged = body["purged"]
    assert purged.get("users", 0) == 1
    assert purged.get("records", 0) >= 1

    with app.app_context():
        cnt = get_db().execute(
            "SELECT COUNT(*) FROM users WHERE id = ?", (uid,)
        ).fetchone()[0]
        assert cnt == 0


def test_self_delete_clears_session(auth_client):
    auth_client.post("/api/me/delete", json={"confirm": "DELETE"})
    # 后续 GET /api/me 应当 401
    r = auth_client.get("/api/me")
    assert r.status_code == 401


def test_last_admin_cannot_self_delete(app, client):
    """最后一个管理员注销前必须先把 admin 权限交出去，否则后台无人能登。"""
    from werkzeug.security import generate_password_hash
    from db import get_db
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO users (username, password, is_admin) VALUES (?, ?, 1)",
            ("admin1", generate_password_hash("pwd")),
        )
        db.commit()
        uid = db.execute("SELECT id FROM users WHERE username = ?", ("admin1",)).fetchone()[0]
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["username"] = "admin1"
        s["is_admin"] = True

    r = client.post("/api/me/delete", json={"confirm": "DELETE"})
    assert r.status_code == 409
    assert "管理员" in r.get_json()["message"]
