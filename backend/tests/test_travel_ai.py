"""行程 AI 生成:清洗、分步作业、单块草稿不落库。

不打真实 LLM——把 _call_llm 换成返回预设 JSON 的桩,这样测的是我们的流程:
拆步、校验、失败隔离、重试、越权。
"""
from __future__ import annotations

import json
import time

import pytest

from services import travel_ai


# ---------- 清洗 ----------

def test_outline_dates_are_recomputed_not_trusted():
    """模型经常跳号或漏天,日期一律按起始日推算。"""
    out = travel_ai.clean_outline({
        "title": "北欧", "start_date": "2026-10-01", "end_date": "2026-10-04",
        "days": [{"day_no": 1, "route": "A → B", "date": "1999-01-01"},
                 {"day_no": 99, "route": "越界的一天"}],
    })
    assert [d["day_no"] for d in out["days"]] == [1, 2, 3, 4]
    assert [d["date"] for d in out["days"]] == [
        "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]
    assert out["days"][0]["route"] == "A → B"


def test_outline_rejects_bad_dates_and_overlong_trips():
    for bad in ({"start_date": "x", "end_date": "2026-10-04"},
                {"start_date": "2026-10-04", "end_date": "2026-10-01"},
                {"start_date": "2026-01-01", "end_date": "2026-06-01"}):
        with pytest.raises(travel_ai.AIError):
            travel_ai.clean_outline({"title": "t", **bad})


def test_day_detail_drops_bad_coordinates():
    """地图上一个错点比少一个点糟得多,坐标不合法就整点丢掉。"""
    d = travel_ai.clean_day_detail({"stops": [
        {"t": "纬度越界", "lat": 95, "lng": 10},
        {"t": "经度越界", "lat": 10, "lng": 200},
        {"t": "没坐标"},
        {"t": "正常", "lat": 60.17, "lng": 24.92},
        {"t": "正常", "lat": 60.17, "lng": 24.92},      # 重复
    ]})
    assert [s["t"] for s in d["stops"]] == ["正常"]


def test_day_detail_caps_and_normalizes():
    d = travel_ai.clean_day_detail({
        "sched": [["8:00", "早餐"], ["不是时间", "另一条", "备注", 1]],
        "todo": ["x"] * 20,
        "stay": {"h": "酒店", "a": "地址", "lat": "abc"},
    })
    assert d["sched"][0] == ["8:00", "早餐", "", 0]
    assert d["sched"][1] == ["", "另一条", "备注", 1]     # 非法时间清成空,不丢整条
    assert len(d["todo"]) == 5
    assert "lat" not in d["stay"]


def test_loads_loose_handles_fenced_json():
    assert travel_ai._loads_loose('好的:\n```json\n{"a":1}\n```') == {"a": 1}
    assert travel_ai._loads_loose('{"a":2}') == {"a": 2}
    assert travel_ai._loads_loose("完全不是 JSON") is None


def test_slice_notice_picks_the_right_day():
    notice = "第1天 上海集合\n坐飞机\n第2天 赫尔辛基\n岩石教堂\n第3天 塔林"
    got = travel_ai.slice_notice(notice, {"day_no": 2})
    assert "赫尔辛基" in got and "岩石教堂" in got
    assert "上海集合" not in got and "塔林" not in got
    assert travel_ai.slice_notice(notice, {"day_no": 9}) is None


# ---------- 作业流程 ----------

_OUTLINE = {
    "title": "逃离地球计划", "subtitle": "北欧三国", "code": "T-1",
    "start_date": "2026-10-01", "end_date": "2026-10-03",
    "days": [
        {"day_no": 1, "route": "上海 → 赫尔辛基", "transport": "HO1607", "meal": "晚"},
        {"day_no": 2, "route": "赫尔辛基 → 塔林", "transport": "快船", "meal": "早 / 午"},
        {"day_no": 3, "route": "塔林 → 上海", "transport": "HO1608", "meal": "早"},
    ],
}
_DAY = {
    "sched": [["09:00", "出发", "", 1]],
    "spots": [["岩石教堂", "15min"]],
    "stops": [{"t": "岩石教堂", "lat": 60.173, "lng": 24.925, "desc": "凿进整块花岗岩里的教堂。"}],
    "todo": ["赶上管风琴试音值得多站一会儿"],
    "stay": {"h": "某酒店", "a": "某路 1 号"},
}


def _stub_llm(monkeypatch, *, outline=None, day=None, fail_days=(), block=None):
    """按 endpoint 分派预设回复;fail_days 里的天返回坏 JSON。"""
    calls = []

    def fake(messages, llm=None, tools=None, tool_choice=None,
             temperature=0.3, timeout=10, endpoint="unknown"):
        calls.append(endpoint)
        if endpoint == "travel.outline":
            payload = outline if outline is not None else _OUTLINE
        elif endpoint == "travel.day":
            user = messages[-1]["content"]
            n = next((d for d in (1, 2, 3, 4, 5) if f"第 {d} 天" in user), 0)
            if n in fail_days:
                return {"choices": [{"message": {"content": "抱歉，我写不出来"}}]}
            payload = day if day is not None else _DAY
        else:
            payload = block if block is not None else {"text": "一段介绍草稿。"}
        return {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}

    monkeypatch.setattr("services.llm._call_llm", fake)
    return calls


def _wait(client, job_id, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/trips/ai/jobs/{job_id}").get_json()
        if job["status"] in ("done", "failed", "cancelled"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"任务 {job_id} 超时未结束")


def test_generate_from_idea_builds_trip_and_fills_days(app, auth_client, monkeypatch):
    calls = _stub_llm(monkeypatch)
    r = auth_client.post("/api/trips/ai/generate", json={"idea": "我想去北欧,10 月初,三天"})
    assert r.status_code == 201
    job = _wait(auth_client, r.get_json()["job_id"])

    assert job["status"] == "done"
    assert job["done"] == job["total"] == 4          # 骨架 + 3 天
    assert calls.count("travel.outline") == 1
    assert calls.count("travel.day") == 3

    trip = auth_client.get(f"/api/trips/{job['trip_id']}").get_json()
    assert trip["trip"]["title"] == "逃离地球计划"
    assert len(trip["days"]) == 3
    assert trip["days"][0]["route"] == "上海 → 赫尔辛基"
    assert trip["days"][0]["detail"]["stops"][0]["t"] == "岩石教堂"


def test_one_bad_day_does_not_sink_the_job_and_retry_only_redoes_it(app, auth_client, monkeypatch):
    calls = _stub_llm(monkeypatch, fail_days=(2,))
    job_id = auth_client.post("/api/trips/ai/generate",
                              json={"idea": "北欧三天"}).get_json()["job_id"]
    job = _wait(auth_client, job_id)

    assert job["status"] == "done"                   # 单天失败不拖垮整趟
    steps = {s["key"]: s["status"] for s in job["steps"]}
    assert steps["day-1"] == "done" and steps["day-3"] == "done"
    assert steps["day-2"] == "failed"

    # 重试:只重跑失败那天,已完成的不动
    calls.clear()
    _stub_llm(monkeypatch)                           # 这次都成功
    auth_client.post(f"/api/trips/ai/jobs/{job_id}/retry")
    job2 = _wait(auth_client, job_id)
    assert job2["status"] == "done"
    assert all(s["status"] == "done" for s in job2["steps"])

    trip = auth_client.get(f"/api/trips/{job2['trip_id']}").get_json()
    assert trip["days"][1]["detail"]["sched"]


def test_outline_failure_fails_the_job_with_a_message(app, auth_client, monkeypatch):
    _stub_llm(monkeypatch, outline={"title": "缺日期"})
    job_id = auth_client.post("/api/trips/ai/generate",
                              json={"idea": "随便"}).get_json()["job_id"]
    job = _wait(auth_client, job_id)
    assert job["status"] == "failed"
    assert "日期" in (job["error"] or "")
    assert job["trip_id"] is None                    # 骨架没成就不留半截行程


def test_fill_days_on_existing_trip(app, auth_client, monkeypatch):
    _stub_llm(monkeypatch)
    tid = auth_client.post("/api/trips", json={
        "title": "手建的", "start_date": "2026-10-01", "end_date": "2026-10-02",
    }).get_json()["id"]
    job_id = auth_client.post(f"/api/trips/{tid}/ai/fill", json={}).get_json()["job_id"]
    job = _wait(auth_client, job_id)
    assert job["status"] == "done" and job["trip_id"] == tid
    trip = auth_client.get(f"/api/trips/{tid}").get_json()
    assert all(d["detail"].get("sched") for d in trip["days"])


def test_generate_requires_input(app, auth_client):
    assert auth_client.post("/api/trips/ai/generate", json={}).status_code == 400
    assert auth_client.post("/api/trips/ai/generate",
                            json={"notice": "x" * 20001}).status_code == 400


# ---------- 单块草稿 ----------

def test_block_returns_draft_without_saving(app, auth_client, monkeypatch):
    """AI 写的东西不能直接盖掉用户的内容——接口只返回草稿。"""
    _stub_llm(monkeypatch, block={"text": "凿进整块花岗岩里的教堂,声学极好。"})
    tid = auth_client.post("/api/trips", json={
        "title": "t", "start_date": "2026-10-01", "end_date": "2026-10-02",
    }).get_json()["id"]
    auth_client.patch(f"/api/trips/{tid}/days/1", json={
        "detail": {"stops": [{"t": "岩石教堂", "lat": 60.17, "lng": 24.92, "desc": "我自己写的"}]},
    })

    r = auth_client.post(f"/api/trips/{tid}/ai/block",
                         json={"kind": "spot_desc", "day_no": 1, "spot": "岩石教堂"})
    assert r.status_code == 200
    assert "花岗岩" in r.get_json()["text"]

    after = auth_client.get(f"/api/trips/{tid}").get_json()
    assert after["days"][0]["detail"]["stops"][0]["desc"] == "我自己写的"


def test_block_validates_kind_and_ownership(app, auth_client, client, monkeypatch):
    _stub_llm(monkeypatch)
    tid = auth_client.post("/api/trips", json={
        "title": "t", "start_date": "2026-10-01", "end_date": "2026-10-02",
    }).get_json()["id"]
    assert auth_client.post(f"/api/trips/{tid}/ai/block",
                            json={"kind": "不存在的"}).status_code == 400
    assert auth_client.post(f"/api/trips/{tid}/ai/block",
                            json={"kind": "spot_desc"}).status_code == 400   # 缺 spot

    from werkzeug.security import generate_password_hash
    from db import get_db
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO users (username, password, is_admin) VALUES (?,?,0)",
                   ("other", generate_password_hash("p")))
        db.commit()
        other = db.execute("SELECT id FROM users WHERE username='other'").fetchone()[0]
    with client.session_transaction() as s:
        s["user_id"] = other
        s["username"] = "other"
    assert client.post(f"/api/trips/{tid}/ai/block",
                       json={"kind": "spot_desc", "spot": "x"}).status_code == 404
    assert client.post(f"/api/trips/{tid}/ai/fill", json={}).status_code == 404


def test_block_list_kinds_are_cleaned(app, auth_client, monkeypatch):
    _stub_llm(monkeypatch, block={"items": ["一条", "", "  ", "另一条"] + ["多"] * 9})
    tid = auth_client.post("/api/trips", json={
        "title": "t", "start_date": "2026-10-01", "end_date": "2026-10-02",
    }).get_json()["id"]
    items = auth_client.post(f"/api/trips/{tid}/ai/block",
                             json={"kind": "day_tips", "day_no": 1}).get_json()["items"]
    assert "" not in items and len(items) <= 5


def test_job_is_scoped_to_its_owner(app, auth_client, client, monkeypatch):
    _stub_llm(monkeypatch)
    job_id = auth_client.post("/api/trips/ai/generate",
                              json={"idea": "北欧"}).get_json()["job_id"]
    _wait(auth_client, job_id)
    from werkzeug.security import generate_password_hash
    from db import get_db
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO users (username, password, is_admin) VALUES (?,?,0)",
                   ("peeper", generate_password_hash("p")))
        db.commit()
        uid = db.execute("SELECT id FROM users WHERE username='peeper'").fetchone()[0]
    with client.session_transaction() as s:
        s["user_id"] = uid
    assert client.get(f"/api/trips/ai/jobs/{job_id}").status_code == 404
