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


# ---------- 速查信息 + 分享可见性 ----------

def test_facts_crud_and_default_private(app, auth_client):
    tid = _mk_trip(auth_client).get_json()["id"]
    r = auth_client.post(f"/api/trips/{tid}/facts", json={
        "label": "领队", "body": "臧华男 13945079235 导游证 AB99274K"})
    assert r.status_code == 201
    fid = r.get_json()["id"]

    facts = auth_client.get(f"/api/trips/{tid}").get_json()["facts"]
    assert facts[0]["label"] == "领队"
    assert facts[0]["is_public"] == 0        # 默认不公开

    assert auth_client.patch(f"/api/trips/{tid}/facts/{fid}",
                             json={"is_public": True}).status_code == 200
    assert auth_client.get(f"/api/trips/{tid}").get_json()["facts"][0]["is_public"] == 1

    assert auth_client.delete(f"/api/trips/{tid}/facts/{fid}").status_code == 200
    assert auth_client.get(f"/api/trips/{tid}").get_json()["facts"] == []


def test_public_share_respects_fact_visibility(app, auth_client):
    """领队/使馆电话这类默认不进分享页;逐条打开后才出现,且只给 label/body。"""
    tid = _mk_trip(auth_client).get_json()["id"]
    auth_client.post(f"/api/trips/{tid}/facts",
                     json={"label": "领队", "body": "臧华男 13945079235"})
    pub_id = auth_client.post(f"/api/trips/{tid}/facts",
                              json={"label": "航班", "body": "HO1607 PVG–HEL"}).get_json()["id"]
    auth_client.patch(f"/api/trips/{tid}/facts/{pub_id}", json={"is_public": True})
    auth_client.post(f"/api/trips/{tid}/packing", json={"grp": "证件", "label": "护照"})
    token = auth_client.post(f"/api/trips/{tid}/share").get_json()["token"]

    anon = app.test_client()
    body = anon.get(f"/api/public/trips/{token}")
    raw = body.get_data(as_text=True)
    data = body.get_json()

    labels = [f["label"] for f in data["facts"]]
    assert labels == ["航班"]                 # 只有显式公开的那条
    assert "13945079235" not in raw           # 领队手机号没泄露
    assert "护照" not in raw                  # 打包清单始终不公开
    assert "is_public" not in raw and "sort_order" not in raw


# ---------- 景点照片 ----------

# 1×1 的 PNG，够走完落盘 / 取图这条链路
_PNG = ("data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def _share_token(client, tid):
    return client.post(f"/api/trips/{tid}/share").get_json()["token"]


def test_photo_upload_and_fetch(app, auth_client, tmp_path, monkeypatch):
    monkeypatch.setattr("services.trip_photos._UPLOAD_BASE", str(tmp_path))
    tid = _mk_trip(auth_client).get_json()["id"]

    r = auth_client.post(f"/api/trips/{tid}/photos", json={"image": _PNG})
    assert r.status_code == 201
    sha = r.get_json()["sha256"]
    assert len(sha) == 64

    # 同一张图再传一次只是去重，不会多占磁盘
    again = auth_client.post(f"/api/trips/{tid}/photos", json={"image": _PNG})
    assert again.get_json() == {"sha256": sha, "deduped": True}

    got = auth_client.get(f"/api/trips/{tid}/photos/{sha}")
    assert got.status_code == 200
    assert got.mimetype == "image/png"


def test_photo_rejects_garbage(app, auth_client, tmp_path, monkeypatch):
    monkeypatch.setattr("services.trip_photos._UPLOAD_BASE", str(tmp_path))
    tid = _mk_trip(auth_client).get_json()["id"]
    assert auth_client.post(f"/api/trips/{tid}/photos", json={"image": ""}).status_code == 400
    assert auth_client.post(f"/api/trips/{tid}/photos",
                            json={"image": "data:image/gif;base64,R0lGODlhAQABAAAAACw="}
                            ).status_code == 400


def test_photo_public_only_via_valid_share(app, auth_client, tmp_path, monkeypatch):
    """分享页要能匿名取图，但只认这趟行程的 token + 这趟行程名下的 sha。"""
    monkeypatch.setattr("services.trip_photos._UPLOAD_BASE", str(tmp_path))
    tid = _mk_trip(auth_client).get_json()["id"]
    sha = auth_client.post(f"/api/trips/{tid}/photos", json={"image": _PNG}).get_json()["sha256"]
    token = _share_token(auth_client, tid)

    anon = app.test_client()
    assert anon.get(f"/api/public/trips/{token}/photos/{sha}").status_code == 200
    # 私有端点仍然要登录
    assert anon.get(f"/api/trips/{tid}/photos/{sha}").status_code == 401
    # 撤销后立刻取不到
    auth_client.delete(f"/api/trips/{tid}/share")
    assert anon.get(f"/api/public/trips/{token}/photos/{sha}").status_code == 404


def test_photo_sha_scoped_to_trip(app, auth_client, tmp_path, monkeypatch):
    """拿 A 行程的 sha 配 B 行程的分享链接，取不到。"""
    monkeypatch.setattr("services.trip_photos._UPLOAD_BASE", str(tmp_path))
    a = _mk_trip(auth_client, title="A").get_json()["id"]
    b = _mk_trip(auth_client, title="B").get_json()["id"]
    sha = auth_client.post(f"/api/trips/{a}/photos", json={"image": _PNG}).get_json()["sha256"]
    token_b = _share_token(auth_client, b)

    anon = app.test_client()
    assert anon.get(f"/api/public/trips/{token_b}/photos/{sha}").status_code == 404
    assert auth_client.get(f"/api/trips/{b}/photos/{sha}").status_code == 404


def test_photo_path_traversal_rejected(app, auth_client, tmp_path, monkeypatch):
    monkeypatch.setattr("services.trip_photos._UPLOAD_BASE", str(tmp_path))
    tid = _mk_trip(auth_client).get_json()["id"]
    token = _share_token(auth_client, tid)
    anon = app.test_client()
    for bad in ["../../etc/passwd", "a" * 64, "nope", "%2e%2e%2fetc%2fpasswd"]:
        assert anon.get(f"/api/public/trips/{token}/photos/{bad}").status_code in (404, 308)


def test_photo_gc_on_detail_update(app, auth_client, tmp_path, monkeypatch):
    """从停留点上移掉照片后,文件和记录都该被收走,旧链接立刻失效。"""
    monkeypatch.setattr("services.trip_photos._UPLOAD_BASE", str(tmp_path))
    tid = _mk_trip(auth_client).get_json()["id"]
    sha = auth_client.post(f"/api/trips/{tid}/photos", json={"image": _PNG}).get_json()["sha256"]
    token = _share_token(auth_client, tid)

    auth_client.patch(f"/api/trips/{tid}/days/1", json={
        "detail": {"stops": [{"t": "岩石教堂", "lat": 60.17, "lng": 24.92, "photos": [sha]}]},
    })
    anon = app.test_client()
    assert anon.get(f"/api/public/trips/{token}/photos/{sha}").status_code == 200

    # 把照片从停留点上去掉
    auth_client.patch(f"/api/trips/{tid}/days/1", json={
        "detail": {"stops": [{"t": "岩石教堂", "lat": 60.17, "lng": 24.92, "photos": []}]},
    })
    assert anon.get(f"/api/public/trips/{token}/photos/{sha}").status_code == 404
    assert auth_client.get(f"/api/trips/{tid}/photos/{sha}").status_code == 404


def test_photo_gc_keeps_photos_used_by_other_days(app, auth_client, tmp_path, monkeypatch):
    """同一趟行程里别的天还在用这张图,就不能删。"""
    monkeypatch.setattr("services.trip_photos._UPLOAD_BASE", str(tmp_path))
    tid = _mk_trip(auth_client).get_json()["id"]
    sha = auth_client.post(f"/api/trips/{tid}/photos", json={"image": _PNG}).get_json()["sha256"]
    for day in (1, 2):
        auth_client.patch(f"/api/trips/{tid}/days/{day}", json={
            "detail": {"stops": [{"t": f"D{day}", "lat": 60, "lng": 24, "photos": [sha]}]},
        })
    auth_client.patch(f"/api/trips/{tid}/days/1", json={"detail": {"stops": []}})
    assert auth_client.get(f"/api/trips/{tid}/photos/{sha}").status_code == 200


def test_photo_gc_understands_legacy_single_field(app, auth_client, tmp_path, monkeypatch):
    """早先存的是单数的 photo 字段,收尾时不能把它当成没人用。"""
    monkeypatch.setattr("services.trip_photos._UPLOAD_BASE", str(tmp_path))
    tid = _mk_trip(auth_client).get_json()["id"]
    sha = auth_client.post(f"/api/trips/{tid}/photos", json={"image": _PNG}).get_json()["sha256"]
    auth_client.patch(f"/api/trips/{tid}/days/1", json={
        "detail": {"stops": [{"t": "旧数据", "lat": 60, "lng": 24, "photo": sha}]},
    })
    auth_client.patch(f"/api/trips/{tid}/days/2", json={"route": "无关改动"})
    assert auth_client.get(f"/api/trips/{tid}/photos/{sha}").status_code == 200


# ---------- 离线导出 ----------

def _rich_trip(auth_client, tmp_path, monkeypatch):
    monkeypatch.setattr("services.trip_photos._UPLOAD_BASE", str(tmp_path))
    tid = _mk_trip(auth_client).get_json()["id"]
    sha = auth_client.post(f"/api/trips/{tid}/photos", json={"image": _PNG}).get_json()["sha256"]
    auth_client.patch(f"/api/trips/{tid}/days/1", json={
        "route": "上海 → 赫尔辛基",
        "transport": "HO1607",
        "detail": {
            "sched": [["09:05", "起飞", "飞 11 小时", 1]],
            "spots": [["岩石教堂", "15min"]],
            "stops": [{"t": "岩石教堂", "lat": 60.17, "lng": 24.92, "photos": [sha]},
                      {"t": "塔林老城", "lat": 59.44, "lng": 24.75}],
            "todo": ["赶上管风琴试音值得多站一会儿"],
            "stay": {"h": "Heymo 1", "a": "Espoo"},
        },
        "journal": "这是我的私人手记",
    })
    auth_client.post(f"/api/trips/{tid}/packing", json={"grp": "证件", "label": "护照"})
    auth_client.post(f"/api/trips/{tid}/facts",
                     json={"label": "领队", "body": "张三 13800000000"})
    auth_client.post(f"/api/trips/{tid}/facts",
                     json={"label": "时差", "body": "慢 6 小时", "is_public": True})
    return tid


def test_export_html_is_self_contained(app, auth_client, tmp_path, monkeypatch):
    """离线可看的前提:文件里不能有任何外部引用。"""
    tid = _rich_trip(auth_client, tmp_path, monkeypatch)
    r = auth_client.get(f"/api/trips/{tid}/export.html")
    assert r.status_code == 200
    doc = r.data.decode("utf-8")

    assert "<!DOCTYPE html>" in doc and "window.print()" in doc
    assert "data:image/png;base64," in doc          # 照片内嵌
    for bad in ("http://", "https://", "<script src", "<link rel=\"stylesheet\""):
        assert bad not in doc, f"导出的文件里不该出现 {bad}"
    assert 'filename*=UTF-8' in r.headers["Content-Disposition"]
    assert r.headers["Content-Type"].count("charset") == 1


def test_export_full_vs_share_scope(app, auth_client, tmp_path, monkeypatch):
    """完整版给自己看;分享版口径和分享链接一致。"""
    tid = _rich_trip(auth_client, tmp_path, monkeypatch)
    full = auth_client.get(f"/api/trips/{tid}/export.html").data.decode()
    assert "这是我的私人手记" in full and "护照" in full and "13800000000" in full

    share = auth_client.get(f"/api/trips/{tid}/export.html?scope=share").data.decode()
    assert "这是我的私人手记" not in share      # 手记
    assert "护照" not in share                  # 打包清单
    assert "13800000000" not in share           # 私密速查
    assert "慢 6 小时" in share                 # 公开速查还在
    assert "岩石教堂" in share


def test_export_can_skip_photos(app, auth_client, tmp_path, monkeypatch):
    tid = _rich_trip(auth_client, tmp_path, monkeypatch)
    doc = auth_client.get(f"/api/trips/{tid}/export.html?photos=0").data.decode()
    assert "data:image/png;base64," not in doc
    assert "岩石教堂" in doc


def test_export_escapes_user_content(app, auth_client, tmp_path, monkeypatch):
    """行程里的文字是用户和模型写的,拼进 HTML 前必须转义。"""
    tid = _mk_trip(auth_client, title="<img src=x onerror=alert(1)>").get_json()["id"]
    auth_client.patch(f"/api/trips/{tid}/days/1",
                      json={"route": "<script>bad()</script>"})
    doc = auth_client.get(f"/api/trips/{tid}/export.html").data.decode()
    assert "<img src=x onerror" not in doc
    assert "<script>bad()</script>" not in doc
    assert "&lt;script&gt;" in doc


def test_export_is_owner_only(app, auth_client, client):
    tid = _mk_trip(auth_client).get_json()["id"]
    assert app.test_client().get(f"/api/trips/{tid}/export.html").status_code == 401
    from werkzeug.security import generate_password_hash
    from db import get_db
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO users (username, password, is_admin) VALUES (?,?,0)",
                   ("nosy", generate_password_hash("p")))
        db.commit()
        uid = db.execute("SELECT id FROM users WHERE username='nosy'").fetchone()[0]
    with client.session_transaction() as s:
        s["user_id"] = uid
    assert client.get(f"/api/trips/{tid}/export.html").status_code == 404
