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
