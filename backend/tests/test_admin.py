"""管理员路由:权限边界 + batch_delete 调用 purge_user_data 正确级联。"""
from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash


@pytest.fixture
def admin_client(app, client):
    """注册一个 is_admin=1 的用户并登录,返回 client。"""
    from db import get_db

    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO users (username, password, is_admin) VALUES (?, ?, 1)",
            ("rootadmin", generate_password_hash("pwd")),
        )
        db.commit()
        uid = db.execute(
            "SELECT id FROM users WHERE username = ?", ("rootadmin",)
        ).fetchone()[0]

    with client.session_transaction() as s:
        s["user_id"] = uid
        s["username"] = "rootadmin"
        s["is_admin"] = True
    return client


def test_list_users_rejects_non_admin(auth_client):
    r = auth_client.get("/api/users")
    # 非 admin 用户必须被拒绝(admin_required 装饰器统一走 403)
    assert r.status_code == 403


def test_list_users_for_admin_excludes_self(app, admin_client):
    """admin 看到的列表里不应包含自己,避免误删自己的入口。"""
    from db import get_db

    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO users (username, password, is_admin) VALUES (?, ?, 0)",
            ("alice", generate_password_hash("pwd")),
        )
        db.commit()

    r = admin_client.get("/api/users")
    assert r.status_code == 200
    rows = r.get_json()
    names = [u["username"] for u in rows]
    assert "alice" in names
    assert "rootadmin" not in names


def test_batch_delete_purges_user_data(app, admin_client):
    """batch_delete 应走 db.purge_user_data,级联清理所有业务表;返回 counts。"""
    from db import get_db

    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO users (username, password, is_admin) VALUES (?, ?, 0)",
            ("bob", generate_password_hash("pwd")),
        )
        db.commit()
        bob_id = db.execute(
            "SELECT id FROM users WHERE username = ?", ("bob",)
        ).fetchone()[0]
        db.execute(
            "INSERT INTO records (user_id, category, amount, note, date) "
            "VALUES (?, '餐饮', 50, '', '2026-06-01')",
            (bob_id,),
        )
        db.commit()

    r = admin_client.post("/api/users/batch_delete", json={"user_ids": [bob_id]})
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert "purged" in body
    # users 表里至少删了 1 条;records 表至少删了 1 条
    purged = body["purged"]
    assert purged.get("users", 0) >= 1
    assert purged.get("records", 0) >= 1

    with app.app_context():
        remain = get_db().execute(
            "SELECT id FROM users WHERE username = ?", ("bob",)
        ).fetchone()
        assert remain is None


def test_batch_delete_refuses_self(app, admin_client):
    """admin 不能通过 batch_delete 删自己——路由层会把请求里的自身 id 过滤掉。"""
    from db import get_db

    with app.app_context():
        admin_id = get_db().execute(
            "SELECT id FROM users WHERE username = ?", ("rootadmin",)
        ).fetchone()[0]

    r = admin_client.post("/api/users/batch_delete", json={"user_ids": [admin_id]})
    assert r.status_code == 200
    body = r.get_json()
    assert body["purged"] == {}

    with app.app_context():
        still_there = get_db().execute(
            "SELECT id FROM users WHERE username = ?", ("rootadmin",)
        ).fetchone()
        assert still_there is not None
