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


def test_day_detail_drops_bad_coordinates_but_keeps_the_place():
    """坐标不合法就把坐标丢掉——地图上一个错点比少一个点糟得多。

    地点本身留着:它在地点列表里看得见、能挂照片,之后补上坐标就会出现在
    地图上。以前是整条丢,结果行程单里明明有的地方就这么没了。
    """
    d = travel_ai.clean_day_detail({"stops": [
        {"t": "纬度越界", "lat": 95, "lng": 10},
        {"t": "经度越界", "lat": 10, "lng": 200},
        {"t": "没坐标"},
        {"t": "正常", "lat": 60.17, "lng": 24.92},
        {"t": "正常", "lat": 60.17, "lng": 24.92},      # 重复
    ]})
    assert [s["t"] for s in d["stops"]] == ["纬度越界", "经度越界", "没坐标", "正常"]
    assert [s["t"] for s in d["stops"] if "lat" in s] == ["正常"]


def test_spots_and_stops_become_one_list():
    """地点只有一份。同名的把时长补上去,坐标/介绍不动;
    只在 spots 里出现的接在后面(没坐标,地图上不画)。"""
    d = travel_ai.clean_day_detail({
        "spots": [["岩石教堂", "15min"], ["只在景点里的地方", "30min"]],
        "stops": [{"t": "岩石教堂", "lat": 60.17, "lng": 24.92, "desc": "凿进花岗岩里。"}],
    })
    assert "spots" not in d
    assert [s["t"] for s in d["stops"]] == ["岩石教堂", "只在景点里的地方"]
    church = d["stops"][0]
    assert church["dur"] == "15min" and church["desc"] == "凿进花岗岩里。"
    assert church["lat"] == 60.17
    assert "lat" not in d["stops"][1]


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
    "stops": [{"t": "岩石教堂", "dur": "15min", "lat": 60.173, "lng": 24.925,
               "desc": "凿进整块花岗岩里的教堂。"}],
    "todo": ["赶上管风琴试音值得多站一会儿"],
    "stay": {"h": "某酒店", "a": "某路 1 号"},
}


_PACKING = {"items": [{"grp": "外层", "label": "冲锋衣", "hint": "风大"},
                      {"grp": "电器", "label": "转换插头", "hint": None}]}


def _stub_llm(monkeypatch, *, outline=None, day=None, fail_days=(), block=None,
              facts=None, packing=None):
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
        elif endpoint == "travel.facts_extract":
            payload = facts if facts is not None else {"items": []}
        elif endpoint == "travel.block.packing":
            payload = packing if packing is not None else _PACKING
        else:
            payload = block if block is not None else {"text": "一段介绍草稿。"}
        return {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}

    monkeypatch.setattr("services.llm._call_llm", fake)
    return calls


def _wait(client, job_id, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/ai-jobs/{job_id}").get_json()
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
    assert job["done"] == job["total"] == 5          # 骨架 + 3 天 + 打包
    assert calls.count("travel.outline") == 1
    assert calls.count("travel.day") == 3
    # 一句话生成没有原文,不排「抽速查」那一步——领队电话这类只能从原文来
    assert "travel.facts_extract" not in calls
    assert {s["key"] for s in job["steps"]} >= {"outline", "day-1", "packing"}

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
    assert steps["packing"] == "done"          # 某天失败不影响后面的步骤

    # 重试:只重跑失败那天,已完成的不动
    calls.clear()
    _stub_llm(monkeypatch)                           # 这次都成功
    auth_client.post(f"/api/ai-jobs/{job_id}/retry")
    job2 = _wait(auth_client, job_id)
    assert job2["status"] == "done"
    assert all(s["status"] in ("done", "skipped") for s in job2["steps"])

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

def _block(client, tid, body):
    """发起单块生成并等结果。接口是异步的:POST 只排队,结果轮询取。"""
    r = client.post(f"/api/trips/{tid}/ai/block", json=body)
    assert r.status_code == 201, r.get_json()
    return _wait(client, r.get_json()["job_id"])


def test_block_returns_draft_without_saving(app, auth_client, monkeypatch):
    """AI 写的东西不能直接盖掉用户的内容——作业只把草稿放在结果里。"""
    _stub_llm(monkeypatch, block={"text": "凿进整块花岗岩里的教堂,声学极好。"})
    tid = auth_client.post("/api/trips", json={
        "title": "t", "start_date": "2026-10-01", "end_date": "2026-10-02",
    }).get_json()["id"]
    auth_client.patch(f"/api/trips/{tid}/days/1", json={
        "detail": {"stops": [{"t": "岩石教堂", "lat": 60.17, "lng": 24.92, "desc": "我自己写的"}]},
    })

    job = _block(auth_client, tid, {"kind": "spot_desc", "day_no": 1, "spot": "岩石教堂"})
    assert job["status"] == "done"
    assert "花岗岩" in job["result"]["text"]

    after = auth_client.get(f"/api/trips/{tid}").get_json()
    assert after["days"][0]["detail"]["stops"][0]["desc"] == "我自己写的"


def test_block_post_returns_immediately(app, auth_client, monkeypatch):
    """POST 不能挂着等 LLM:慢的时候连接要占几分钟,nginx 会判超时甚至熔断。"""
    import time as _t

    def slow(messages, **kw):
        _t.sleep(1.2)
        return {"choices": [{"message": {"content": '{"text":"慢慢写出来的"}'}}]}

    monkeypatch.setattr("services.llm._call_llm", slow)
    tid = auth_client.post("/api/trips", json={
        "title": "t", "start_date": "2026-10-01", "end_date": "2026-10-02",
    }).get_json()["id"]

    t0 = _t.time()
    r = auth_client.post(f"/api/trips/{tid}/ai/block",
                         json={"kind": "spot_desc", "spot": "某地"})
    took = _t.time() - t0
    assert r.status_code == 201
    assert took < 0.8, f"POST 花了 {took:.2f}s,说明还在同步等 LLM"

    job = _wait(auth_client, r.get_json()["job_id"])
    assert job["result"]["text"] == "慢慢写出来的"


def test_block_failure_is_reported_on_the_job(app, auth_client, monkeypatch):
    monkeypatch.setattr("services.llm._call_llm",
                        lambda messages, **kw: {"error": {"message": "上游挂了"}})
    tid = auth_client.post("/api/trips", json={
        "title": "t", "start_date": "2026-10-01", "end_date": "2026-10-02",
    }).get_json()["id"]
    job = _block(auth_client, tid, {"kind": "spot_desc", "spot": "某地"})
    assert job["status"] == "failed"
    assert "上游挂了" in (job["error"] or "")
    assert job["result"] is None


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
    items = _block(auth_client, tid, {"kind": "day_tips", "day_no": 1})["result"]["items"]
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
    assert client.get(f"/api/ai-jobs/{job_id}").status_code == 404


# ---------- 导入时的速查与打包 ----------

_NOTICE = """逃离地球计划 团号 T-2026
领队 张三 13800000000
第1天 上海 → 赫尔辛基 HO1607 09:05/14:00
第2天 赫尔辛基 → 塔林
第3天 塔林 → 上海
"""


def test_notice_import_extracts_facts_and_fills_packing(app, auth_client, monkeypatch):
    """行程单里有的(领队 / 航班)从原文抽;打包清单按行程拟。"""
    calls = _stub_llm(monkeypatch, facts={"items": [
        {"label": "领队", "body": "张三 13800000000"},
        {"label": "航班", "body": "HO1607 09:05/14:00"},
    ]})
    job_id = auth_client.post("/api/trips/ai/generate",
                              json={"notice": _NOTICE}).get_json()["job_id"]
    job = _wait(auth_client, job_id)
    assert job["status"] == "done"
    assert "travel.facts_extract" in calls

    got = auth_client.get(f"/api/trips/{job['trip_id']}").get_json()
    labels = [f["label"] for f in got["facts"]]
    assert labels == ["领队", "航班"]
    # 里面可能有领队手机号,是第三方个人信息,默认不跟着分享链接出去
    assert all(f["is_public"] == 0 for f in got["facts"])
    assert [p["label"] for p in got["packing"]] == ["冲锋衣", "转换插头"]


def test_facts_step_skipped_when_notice_has_nothing(app, auth_client, monkeypatch):
    """原文里一条都没有就老实跳过,不编。"""
    _stub_llm(monkeypatch, facts={"items": []})
    job_id = auth_client.post("/api/trips/ai/generate",
                              json={"notice": _NOTICE}).get_json()["job_id"]
    job = _wait(auth_client, job_id)
    steps = {s["key"]: s["status"] for s in job["steps"]}
    assert steps["facts"] == "skipped"
    assert auth_client.get(f"/api/trips/{job['trip_id']}").get_json()["facts"] == []


def test_extras_do_not_overwrite_existing(app, auth_client, monkeypatch):
    """补全已有行程时,不能把用户整理好的速查和打包盖掉。"""
    _stub_llm(monkeypatch, facts={"items": [{"label": "AI 的", "body": "x"}]})
    tid = auth_client.post("/api/trips", json={
        "title": "手建的", "start_date": "2026-10-01", "end_date": "2026-10-02",
    }).get_json()["id"]
    auth_client.post(f"/api/trips/{tid}/facts", json={"label": "我写的", "body": "别动"})
    auth_client.post(f"/api/trips/{tid}/packing", json={"label": "我的护照"})

    job_id = auth_client.post(f"/api/trips/{tid}/ai/fill",
                              json={"notice": _NOTICE}).get_json()["job_id"]
    _wait(auth_client, job_id)
    got = auth_client.get(f"/api/trips/{tid}").get_json()
    assert [f["label"] for f in got["facts"]] == ["我写的"]
    assert [p["label"] for p in got["packing"]] == ["我的护照"]


def test_cover_note_is_saved(app, auth_client, monkeypatch):
    _stub_llm(monkeypatch, outline={**_OUTLINE, "cover_note": "十月的极光季,四晚都在圈内。"})
    job_id = auth_client.post("/api/trips/ai/generate",
                              json={"idea": "北欧"}).get_json()["job_id"]
    job = _wait(auth_client, job_id)
    trip = auth_client.get(f"/api/trips/{job['trip_id']}").get_json()["trip"]
    assert trip["cover_note"] == "十月的极光季,四晚都在圈内。"


def test_jobs_list_lets_you_come_back(app, auth_client, monkeypatch):
    """离开页面再回来要能接上:列表给最近的任务。"""
    _stub_llm(monkeypatch)
    job_id = auth_client.post("/api/trips/ai/generate",
                              json={"idea": "北欧"}).get_json()["job_id"]
    _wait(auth_client, job_id)
    jobs = auth_client.get("/api/ai-jobs").get_json()
    assert jobs[0]["id"] == job_id
    assert jobs[0]["status"] == "done"
    assert jobs[0]["trip_id"]


# ---------- 行程单文件导入 ----------

def _docx(paragraphs):
    """造一个最小 .docx——它就是个 zip,正文在 word/document.xml 里。"""
    import io as _io
    import zipfile
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    doc = ('<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
           f'wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>')
    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", doc)
    return buf.getvalue()


def _upload(client, name, data):
    import io as _io
    return client.post("/api/trips/ai/extract", content_type="multipart/form-data",
                       data={"file": (_io.BytesIO(data), name)})


def test_extract_docx(app, auth_client):
    r = _upload(auth_client, "行程单.docx",
                _docx(["逃离地球计划 团号 T-1", "第1天 上海 → 赫尔辛基 HO1607",
                       "第2天 赫尔辛基 → 塔林 快船", "领队 张三 13800000000"]))
    assert r.status_code == 200
    text = r.get_json()["text"]
    assert "第1天 上海 → 赫尔辛基 HO1607" in text
    assert "13800000000" in text


def test_extract_html_drops_script_and_style(app, auth_client):
    html = ('<html><head><style>p{color:red}</style></head><body>'
            '<h1>逃离地球计划</h1><table><tr><td>第1天</td><td>上海 → 赫尔辛基</td></tr></table>'
            '<p>领队 张三 13800000000</p><script>alert(1)</script></body></html>')
    text = _upload(auth_client, "x.html", html.encode()).get_json()["text"]
    assert "上海 → 赫尔辛基" in text and "13800000000" in text
    assert "alert(1)" not in text and "color:red" not in text


def test_extract_txt_handles_gbk(app, auth_client):
    """旅行社的 txt 十有八九是 GBK,别读成乱码。"""
    raw = "第1天 上海 → 赫尔辛基\n第2天 塔林 快船\n领队 张三".encode("gb18030")
    text = _upload(auth_client, "x.txt", raw).get_json()["text"]
    assert "赫尔辛基" in text


def test_extract_rejects_unsupported_with_a_useful_message(app, auth_client):
    for name, data, hint in [
        ("x.doc", b"old binary" * 10, ".docx"),
        ("x.xlsx", b"whatever" * 10, "粘贴"),
        ("x.docx", b"not a zip" * 10, "打不开"),
    ]:
        r = _upload(auth_client, name, data)
        assert r.status_code == 400
        assert hint in r.get_json()["error"]


def test_extract_requires_login(app, auth_client):
    import io as _io
    anon = app.test_client()
    r = anon.post("/api/trips/ai/extract", content_type="multipart/form-data",
                  data={"file": (_io.BytesIO(b"x" * 50), "x.txt")})
    assert r.status_code in (401, 403)


# ---------- 主题色 ----------

def test_accent_comes_from_ai_when_not_chosen(app, auth_client, monkeypatch):
    _stub_llm(monkeypatch, outline={**_OUTLINE, "accent": "aurora"})
    job_id = auth_client.post("/api/trips/ai/generate",
                              json={"idea": "去冰岛看极光"}).get_json()["job_id"]
    job = _wait(auth_client, job_id)
    trip = auth_client.get(f"/api/trips/{job['trip_id']}").get_json()["trip"]
    assert trip["accent"] == "aurora"


def test_user_choice_beats_ai(app, auth_client, monkeypatch):
    _stub_llm(monkeypatch, outline={**_OUTLINE, "accent": "aurora"})
    job_id = auth_client.post("/api/trips/ai/generate",
                              json={"idea": "去冰岛", "accent": "sakura"}).get_json()["job_id"]
    job = _wait(auth_client, job_id)
    trip = auth_client.get(f"/api/trips/{job['trip_id']}").get_json()["trip"]
    assert trip["accent"] == "sakura"


def test_bogus_accent_from_ai_falls_back(app, auth_client, monkeypatch):
    _stub_llm(monkeypatch, outline={**_OUTLINE, "accent": "rainbow"})
    job_id = auth_client.post("/api/trips/ai/generate",
                              json={"idea": "随便"}).get_json()["job_id"]
    job = _wait(auth_client, job_id)
    trip = auth_client.get(f"/api/trips/{job['trip_id']}").get_json()["trip"]
    assert trip["accent"] == "glacier"


# ---------- 年份 ----------

def test_ai_picked_dates_are_pushed_into_the_future(app, auth_client, monkeypatch):
    """模型对"今天"没有可靠概念,常按训练时的年份排。没给日期时整段顺延。"""
    from datetime import date, timedelta
    last_year = date.today().replace(year=date.today().year - 1)
    _stub_llm(monkeypatch, outline={
        **_OUTLINE,
        "start_date": last_year.strftime("%Y-%m-%d"),
        "end_date": (last_year + timedelta(days=2)).strftime("%Y-%m-%d"),
    })
    job_id = auth_client.post("/api/trips/ai/generate",
                              json={"idea": "十月去看极光"}).get_json()["job_id"]
    job = _wait(auth_client, job_id)
    trip = auth_client.get(f"/api/trips/{job['trip_id']}").get_json()["trip"]
    start = date.fromisoformat(trip["start_date"])
    assert start >= date.today()
    # 只按整年挪,月份和日子要保住——"十月看极光"不能被改成别的月份
    assert (start.month, start.day) == (last_year.month, last_year.day)


def test_user_given_dates_are_never_shifted(app, auth_client, monkeypatch):
    """用户自己给了日期就照用,哪怕是过去——他可能在补录走过的行程。"""
    from datetime import date
    last_year = date.today().replace(year=date.today().year - 1)
    _stub_llm(monkeypatch, outline={**_OUTLINE,
                                    "start_date": last_year.strftime("%Y-%m-%d"),
                                    "end_date": last_year.strftime("%Y-%m-%d")})
    job_id = auth_client.post("/api/trips/ai/generate", json={
        "idea": "补录去年那趟",
        "start_date": last_year.strftime("%Y-%m-%d"),
        "end_date": last_year.strftime("%Y-%m-%d"),
    }).get_json()["job_id"]
    job = _wait(auth_client, job_id)
    trip = auth_client.get(f"/api/trips/{job['trip_id']}").get_json()["trip"]
    assert trip["start_date"] == last_year.strftime("%Y-%m-%d")


def test_notice_dates_are_never_shifted(app, auth_client, monkeypatch):
    """行程单里的日期是白纸黑字写着的,可能是已经走完的行程,不能改。"""
    from datetime import date
    last_year = date.today().replace(year=date.today().year - 1)
    _stub_llm(monkeypatch, outline={**_OUTLINE,
                                    "start_date": last_year.strftime("%Y-%m-%d"),
                                    "end_date": last_year.strftime("%Y-%m-%d")})
    job_id = auth_client.post("/api/trips/ai/generate",
                              json={"notice": _NOTICE}).get_json()["job_id"]
    job = _wait(auth_client, job_id)
    trip = auth_client.get(f"/api/trips/{job['trip_id']}").get_json()["trip"]
    assert trip["start_date"] == last_year.strftime("%Y-%m-%d")


def test_today_is_in_the_prompt(app, auth_client, monkeypatch):
    """光靠后处理不够,提示词里也得写明今天是哪天。"""
    from datetime import date
    seen = []

    def fake(messages, **kw):
        seen.append(messages[-1]["content"])
        import json as _json
        return {"choices": [{"message": {"content": _json.dumps(_OUTLINE)}}]}

    monkeypatch.setattr("services.llm._call_llm", fake)
    job_id = auth_client.post("/api/trips/ai/generate",
                              json={"idea": "去冰岛"}).get_json()["job_id"]
    _wait(auth_client, job_id)
    assert date.today().strftime("%Y-%m-%d") in seen[0]


# ---------- 批量补景点介绍 ----------

_SPOTS_DAY = {
    "stops": [
        {"t": "岩石教堂", "lat": 60.17, "lng": 24.92},
        {"t": "西贝柳斯公园", "lat": 60.18, "lng": 24.91, "desc": "我自己写的,别动"},
        {"t": "赫尔辛基机场", "lat": 60.32, "lng": 24.96},
    ],
}


def _trip_with_bare_stops(auth_client, days=2):
    tid = auth_client.post("/api/trips", json={
        "title": "老行程", "start_date": "2026-10-01",
        "end_date": f"2026-10-0{days}",
    }).get_json()["id"]
    for n in range(1, days + 1):
        auth_client.patch(f"/api/trips/{tid}/days/{n}",
                          json={"route": f"第 {n} 天", "detail": _SPOTS_DAY})
    return tid


def _stub_spots(monkeypatch, items=None, fail_days=()):
    calls = []

    def fake(messages, llm=None, tools=None, tool_choice=None,
             temperature=0.3, timeout=10, endpoint="unknown"):
        calls.append(endpoint)
        user = messages[-1]["content"]
        n = next((d for d in (1, 2, 3) if f"第 {d} 天" in user), 0)
        if n in fail_days:
            return {"choices": [{"message": {"content": "写不出来"}}]}
        payload = {"items": items if items is not None else [
            {"t": "岩石教堂", "desc": "凿进整块花岗岩里的教堂,声学极好。"},
            {"t": "赫尔辛基机场", "desc": "芬兰的门户,到市区半小时。"},
            {"t": "西贝柳斯公园", "desc": "这条不该被写进去"},
        ]}
        return {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}

    monkeypatch.setattr("services.llm._call_llm", fake)
    return calls


def test_fill_spots_only_fills_empty_ones(app, auth_client, monkeypatch):
    """核心约束:已经写过的介绍一个字都不能动。"""
    calls = _stub_spots(monkeypatch)
    tid = _trip_with_bare_stops(auth_client)
    job_id = auth_client.post(f"/api/trips/{tid}/ai/spots", json={}).get_json()["job_id"]
    job = _wait(auth_client, job_id)
    assert job["status"] == "done"

    stops = auth_client.get(f"/api/trips/{tid}").get_json()["days"][0]["detail"]["stops"]
    by = {s["t"]: s.get("desc") for s in stops}
    assert "花岗岩" in by["岩石教堂"]
    assert "门户" in by["赫尔辛基机场"]
    assert by["西贝柳斯公园"] == "我自己写的,别动"      # 模型给了也不采纳


def test_fill_spots_is_one_call_per_day(app, auth_client, monkeypatch):
    """按天批量,不是一个点一次——六七十个点一个个调又慢又贵。"""
    calls = _stub_spots(monkeypatch)
    tid = _trip_with_bare_stops(auth_client, days=2)
    job_id = auth_client.post(f"/api/trips/{tid}/ai/spots", json={}).get_json()["job_id"]
    job = _wait(auth_client, job_id)
    assert calls.count("travel.spot_descs") == 2
    assert [s["key"] for s in job["steps"]] == ["spots-1", "spots-2"]
    assert all(s["status"] == "done" for s in job["steps"])


def test_fill_spots_skips_names_it_does_not_know(app, auth_client, monkeypatch):
    """名字对不上就丢掉:写回去要按名字配对,配错了比没有还糟。"""
    _stub_spots(monkeypatch, items=[{"t": "根本不存在的地方", "desc": "瞎编的"}])
    tid = _trip_with_bare_stops(auth_client, days=1)
    job_id = auth_client.post(f"/api/trips/{tid}/ai/spots", json={}).get_json()["job_id"]
    _wait(auth_client, job_id)
    stops = auth_client.get(f"/api/trips/{tid}").get_json()["days"][0]["detail"]["stops"]
    assert all(not (s.get("desc") or "").strip() or s["t"] == "西贝柳斯公园" for s in stops)


def test_fill_spots_one_bad_day_does_not_sink_the_rest(app, auth_client, monkeypatch):
    _stub_spots(monkeypatch, fail_days=(1,))
    tid = _trip_with_bare_stops(auth_client, days=2)
    job_id = auth_client.post(f"/api/trips/{tid}/ai/spots", json={}).get_json()["job_id"]
    job = _wait(auth_client, job_id)
    steps = {s["key"]: s["status"] for s in job["steps"]}
    assert steps["spots-1"] == "failed" and steps["spots-2"] == "done"
    assert job["status"] == "done"


def test_fill_spots_has_no_steps_when_nothing_is_missing(app, auth_client, monkeypatch):
    calls = _stub_spots(monkeypatch)
    tid = _trip_with_bare_stops(auth_client, days=1)
    auth_client.post(f"/api/trips/{tid}/ai/spots", json={})
    _wait(auth_client, auth_client.post(f"/api/trips/{tid}/ai/spots",
                                       json={}).get_json()["job_id"])
    calls.clear()
    job_id = auth_client.post(f"/api/trips/{tid}/ai/spots", json={}).get_json()["job_id"]
    job = _wait(auth_client, job_id)
    assert job["steps"] == [] and job["status"] == "done"
    assert not calls                                  # 没有要补的就一次都不调


def test_fill_spots_is_owner_only(app, auth_client, client):
    tid = _trip_with_bare_stops(auth_client, days=1)
    from werkzeug.security import generate_password_hash
    from db import get_db
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO users (username, password, is_admin) VALUES (?,?,0)",
                   ("stranger", generate_password_hash("p")))
        db.commit()
        uid = db.execute("SELECT id FROM users WHERE username='stranger'").fetchone()[0]
    with client.session_transaction() as s:
        s["user_id"] = uid
    assert client.post(f"/api/trips/{tid}/ai/spots", json={}).status_code == 404
