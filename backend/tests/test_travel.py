"""旅行计划:建行程自动铺天、日历数据、手记/打包多端同步、越权隔离。"""
from __future__ import annotations

import json


def _mk_trip(client, **kw):
    payload = {"title": "逃离地球计划", "subtitle": "北欧四国",
               "start_date": "2026-09-26", "end_date": "2026-09-29",
               "accent": "glacier"}
    payload.update(kw)
    return client.post("/api/trips", json=payload)


def test_create_trip_auto_fills_days(app, auth_client):
    """建行程时按起止日期自动铺每一天——日历需要每天都有格子。"""
    r = _mk_trip(auth_client)
    assert r.status_code == 201
    tid = r.get_json()["id"]

    got = auth_client.get(f"/api/trips/{tid}").get_json()
    assert got["trip"]["title"] == "逃离地球计划"
    assert len(got["days"]) == 4                      # 9/26~9/29
    assert [d["day_no"] for d in got["days"]] == [1, 2, 3, 4]
    assert got["days"][0]["date"] == "2026-09-26"
    assert got["days"][-1]["date"] == "2026-09-29"
    assert got["days"][0]["detail"] == {}             # 空白待填


def test_reject_bad_dates(app, auth_client):
    assert _mk_trip(auth_client, start_date="2026/09/26").status_code == 400
    assert _mk_trip(auth_client, start_date="2026-09-29",
                    end_date="2026-09-26").status_code == 400
    assert _mk_trip(auth_client, title="").status_code == 400


def test_update_day_detail_and_journal(app, auth_client):
    """当天详情(结构化)+ 手记都入库——原静态页存 localStorage,换设备即丢。"""
    tid = _mk_trip(auth_client).get_json()["id"]
    detail = {
        "sched": [["09:05", "起飞", "约 11 小时"], ["14:00", "落地"]],
        "spots": [["岩石教堂", "15min"]],
        "stay": {"h": "Heymo 1", "a": "Espoo"},
        "stops": [{"t": "赫尔辛基机场", "lat": 60.317, "lng": 24.963, "air": 1}],
    }
    r = auth_client.patch(f"/api/trips/{tid}/days/1", json={
        "route": "上海 → 赫尔辛基", "transport": "HO1607", "meal": "晚",
        "detail": detail, "journal": "第一天有点累",
    })
    assert r.status_code == 200

    day1 = auth_client.get(f"/api/trips/{tid}").get_json()["days"][0]
    assert day1["route"] == "上海 → 赫尔辛基"
    assert day1["journal"] == "第一天有点累"
    assert day1["detail"]["stay"]["h"] == "Heymo 1"
    assert day1["detail"]["stops"][0]["lat"] == 60.317


def test_packing_checklist_roundtrip(app, auth_client):
    tid = _mk_trip(auth_client).get_json()["id"]
    r = auth_client.post(f"/api/trips/{tid}/packing",
                         json={"grp": "证件", "label": "护照", "hint": "别忘旧护照"})
    assert r.status_code == 201
    item_id = r.get_json()["id"]

    auth_client.patch(f"/api/trips/{tid}/packing/{item_id}", json={"checked": True})
    packs = auth_client.get(f"/api/trips/{tid}").get_json()["packing"]
    assert packs[0]["label"] == "护照" and packs[0]["checked"] == 1

    assert auth_client.delete(f"/api/trips/{tid}/packing/{item_id}").status_code == 200
    assert auth_client.get(f"/api/trips/{tid}").get_json()["packing"] == []


def test_trip_list_status_and_soft_delete(app, auth_client):
    tid = _mk_trip(auth_client).get_json()["id"]
    lst = auth_client.get("/api/trips").get_json()
    row = next(t for t in lst if t["id"] == tid)
    assert row["day_count"] == 4
    assert row["status"] in ("upcoming", "ongoing", "past")

    assert auth_client.delete(f"/api/trips/{tid}").status_code == 200
    assert all(t["id"] != tid for t in auth_client.get("/api/trips").get_json())
    assert auth_client.get(f"/api/trips/{tid}").status_code == 404


def test_accent_validated(app, auth_client):
    tid = _mk_trip(auth_client, accent="不存在的色").get_json()["id"]
    # 非法值回落默认,不报错
    assert auth_client.get(f"/api/trips/{tid}").get_json()["trip"]["accent"] == "glacier"
    assert auth_client.patch(f"/api/trips/{tid}", json={"accent": "bogus"}).status_code == 400
    assert auth_client.patch(f"/api/trips/{tid}", json={"accent": "sakura"}).status_code == 200


def test_other_user_cannot_access(app, auth_client, client):
    """行程按 user_id 隔离,别人的 trip_id 一律 404。"""
    tid = _mk_trip(auth_client).get_json()["id"]
    from werkzeug.security import generate_password_hash
    from db import get_db
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO users (username, password, is_admin) VALUES (?,?,0)",
                   ("someoneelse", generate_password_hash("pwd")))
        db.commit()
        other = db.execute("SELECT id FROM users WHERE username='someoneelse'").fetchone()[0]
    with client.session_transaction() as s:
        s["user_id"] = other
        s["username"] = "someoneelse"

    assert client.get(f"/api/trips/{tid}").status_code == 404
    assert client.patch(f"/api/trips/{tid}/days/1", json={"journal": "x"}).status_code == 404
    assert client.delete(f"/api/trips/{tid}").status_code == 404


# ---------- 分享链接:安全边界 ----------

def _shared_trip(auth_client):
    """建一趟带手记和打包清单的行程,并生成分享 token。"""
    tid = _mk_trip(auth_client).get_json()["id"]
    auth_client.patch(f"/api/trips/{tid}/days/1", json={
        "route": "上海 → 赫尔辛基",
        "detail": {"spots": [["岩石教堂", "15min"]]},
        "journal": "这是我的私人手记，绝不能出现在分享页",
    })
    auth_client.post(f"/api/trips/{tid}/packing", json={"grp": "证件", "label": "护照"})
    token = auth_client.post(f"/api/trips/{tid}/share").get_json()["token"]
    return tid, token


def test_public_share_excludes_journal_and_packing(app, auth_client):
    """公开页必须只给行程本身:手记、打包清单、用户信息一律不出现。"""
    tid, token = _shared_trip(auth_client)

    # conftest 的 client 与 auth_client 是同一个对象(只是塞了 session),
    # 必须新开一个 test_client 才是真正的匿名访客。
    anon = app.test_client()
    r = anon.get(f"/api/public/trips/{token}")
    assert r.status_code == 200
    body = r.get_json()

    assert body["trip"]["title"] == "逃离地球计划"
    assert body["days"][0]["route"] == "上海 → 赫尔辛基"
    assert body["days"][0]["detail"]["spots"][0][0] == "岩石教堂"

    # 整个响应体里不能出现手记内容或任何 journal 字段
    raw = r.get_data(as_text=True)
    assert "私人手记" not in raw
    assert "journal" not in raw
    assert "packing" not in body and "护照" not in raw
    # 也不能泄露用户/内部字段
    for leaked in ("user_id", "deleted_at", "detail_json"):
        assert leaked not in raw


def test_public_share_requires_no_login_but_others_still_protected(app, auth_client):
    """公开端点匿名可读;但其它端点对匿名依旧是 401——分享不应打开别的门。"""
    tid, token = _shared_trip(auth_client)
    anon = app.test_client()
    assert anon.get(f"/api/public/trips/{token}").status_code == 200
    assert anon.get("/api/trips").status_code == 401
    assert anon.get(f"/api/trips/{tid}").status_code == 401
    assert anon.get("/api/records").status_code == 401
    assert anon.get("/api/stats/today").status_code == 401


def test_revoke_invalidates_link(app, auth_client):
    tid, token = _shared_trip(auth_client)
    anon = app.test_client()
    assert anon.get(f"/api/public/trips/{token}").status_code == 200
    assert auth_client.delete(f"/api/trips/{tid}/share").status_code == 200
    assert anon.get(f"/api/public/trips/{token}").status_code == 404


def test_soft_deleted_trip_link_dies(app, auth_client):
    tid, token = _shared_trip(auth_client)
    auth_client.delete(f"/api/trips/{tid}")
    assert app.test_client().get(f"/api/public/trips/{token}").status_code == 404


def test_bad_token_404(app):
    anon = app.test_client()
    assert anon.get("/api/public/trips/nope").status_code == 404
    assert anon.get("/api/public/trips/" + "x" * 80).status_code == 404


def test_share_token_reused_and_owner_only(app, auth_client):
    tid, token = _shared_trip(auth_client)
    again = auth_client.post(f"/api/trips/{tid}/share").get_json()
    assert again["token"] == token and again["reused"] is True     # 不会悄悄换掉旧链接

    # 匿名不能生成/撤销分享
    anon = app.test_client()
    assert anon.post(f"/api/trips/{tid}/share").status_code == 401
    assert anon.delete(f"/api/trips/{tid}/share").status_code == 401
