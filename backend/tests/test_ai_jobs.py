"""统一的后台作业:一张表、一个池、一个端点。

以前行程生成和财务体检各有一套(两张表、两个 ThreadPoolExecutor、两个轮询
端点),并发上限互相不知道。这里测合并之后的公共行为:列表筛选、取消、
重试、越权,以及单步/多步作业共存。
"""
from __future__ import annotations

import time

import pytest

from services import ai_jobs


def _wait(client, job_id, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/ai-jobs/{job_id}").get_json()
        if job["status"] in ("done", "failed", "cancelled"):
            return job
        time.sleep(0.03)
    raise AssertionError(f"任务 {job_id} 超时未结束")


@pytest.fixture
def stub_kinds(app):
    """注册几个不打 LLM 的假 runner。"""
    slow = {"go": False}

    def quick(ctx):
        return {"echo": ctx.payload.get("x")}

    def boom(ctx):
        raise RuntimeError("炸了")

    def stepped(ctx):
        steps = [{"key": f"s{i}", "label": f"第 {i} 步", "status": "pending", "error": None}
                 for i in (1, 2, 3)]
        ctx.set_steps(steps)
        for s in steps:
            if ctx.cancelled:
                for t in steps:
                    if t["status"] == "pending":
                        t["status"] = "skipped"
                ctx.set_steps(steps)
                return None
            s["status"] = "done"
            ctx.set_steps(steps)
            time.sleep(0.05)
        return None

    ai_jobs.register("t_quick", quick)
    ai_jobs.register("t_boom", boom)
    ai_jobs.register("t_stepped", stepped)
    return slow


def _submit(app, uid, kind, payload=None, **kw):
    with app.app_context():
        from flask import g
        g.user_id = uid
        return ai_jobs.submit(uid, kind, payload or {}, None, **kw)


def _uid(app):
    from db import get_db
    with app.app_context():
        return get_db().execute("SELECT id FROM users WHERE username='tester'").fetchone()[0]


def test_single_step_job_runs_and_returns_result(app, auth_client, stub_kinds):
    jid = _submit(app, _uid(app), "t_quick", {"x": 42})
    job = _wait(auth_client, jid)
    assert job["status"] == "done"
    assert job["result"] == {"echo": 42}
    assert job["steps"] == []          # 单步作业不记步骤


def test_failed_runner_lands_on_the_job(app, auth_client, stub_kinds):
    jid = _submit(app, _uid(app), "t_boom")
    job = _wait(auth_client, jid)
    assert job["status"] == "failed"
    assert "炸了" in job["error"]


def test_unknown_kind_is_reported_not_swallowed(app, auth_client):
    jid = _submit(app, _uid(app), "没这种东西")
    job = _wait(auth_client, jid)
    assert job["status"] == "failed"
    assert "未注册" in job["error"]


def test_multi_step_progress_is_visible(app, auth_client, stub_kinds):
    jid = _submit(app, _uid(app), "t_stepped")
    job = _wait(auth_client, jid)
    assert job["status"] == "done"
    assert job["done"] == job["total"] == 3
    assert [s["status"] for s in job["steps"]] == ["done"] * 3


def test_cancel_stops_the_remaining_steps(app, auth_client, stub_kinds):
    jid = _submit(app, _uid(app), "t_stepped")
    r = auth_client.post(f"/api/ai-jobs/{jid}/cancel")
    assert r.status_code == 200
    job = _wait(auth_client, jid)
    assert job["status"] == "cancelled"
    # 取消之后 worker 不该把状态又改回 done
    time.sleep(0.3)
    assert auth_client.get(f"/api/ai-jobs/{jid}").get_json()["status"] == "cancelled"


def test_cancel_is_a_noop_once_finished(app, auth_client, stub_kinds):
    jid = _submit(app, _uid(app), "t_quick")
    _wait(auth_client, jid)
    assert auth_client.post(f"/api/ai-jobs/{jid}/cancel").get_json()["success"] is False


def test_retry_reruns_a_finished_job(app, auth_client, stub_kinds):
    jid = _submit(app, _uid(app), "t_boom")
    assert _wait(auth_client, jid)["status"] == "failed"

    ai_jobs.register("t_boom", lambda ctx: {"ok": True})     # 这次不炸
    assert auth_client.post(f"/api/ai-jobs/{jid}/retry").status_code == 200
    job = _wait(auth_client, jid)
    assert job["status"] == "done" and job["result"] == {"ok": True}


def test_retry_refuses_while_running(app, auth_client, stub_kinds):
    jid = _submit(app, _uid(app), "t_stepped")
    assert auth_client.post(f"/api/ai-jobs/{jid}/retry").status_code == 409
    _wait(auth_client, jid)


def test_dedup_key_does_not_queue_twice(app, auth_client, stub_kinds):
    uid = _uid(app)
    a = _submit(app, uid, "t_stepped", dedup_key="same")
    b = _submit(app, uid, "t_stepped", dedup_key="same")
    assert a == b
    _wait(auth_client, a)


def test_list_filters_by_kind(app, auth_client, stub_kinds):
    uid = _uid(app)
    _wait(auth_client, _submit(app, uid, "t_quick"))
    _wait(auth_client, _submit(app, uid, "t_stepped"))

    everything = auth_client.get("/api/ai-jobs").get_json()
    assert {j["kind"] for j in everything} == {"t_quick", "t_stepped"}

    only = auth_client.get("/api/ai-jobs?kinds=t_stepped").get_json()
    assert [j["kind"] for j in only] == ["t_stepped"]
    # 筛掉的那类不该冒出来——旅行页就是靠这个不去显示财务体检的任务
    assert auth_client.get("/api/ai-jobs?kinds=没这种东西").get_json() == []


def test_jobs_are_scoped_to_their_owner(app, auth_client, client, stub_kinds):
    from werkzeug.security import generate_password_hash
    from db import get_db
    with app.app_context():
        conn = get_db()
        conn.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, 0)",
                     ("other", generate_password_hash("pwd")))
        conn.commit()
        oid = conn.execute("SELECT id FROM users WHERE username='other'").fetchone()[0]

    jid = _submit(app, oid, "t_quick")
    assert auth_client.get(f"/api/ai-jobs/{jid}").status_code == 404
    assert auth_client.post(f"/api/ai-jobs/{jid}/cancel").status_code == 404
    assert auth_client.post(f"/api/ai-jobs/{jid}/retry").status_code == 404
    assert auth_client.get("/api/ai-jobs").get_json() == []


def test_orphans_are_reaped_on_boot(app, auth_client, stub_kinds):
    """进程重启会让 pending/running 永远卡住,前端一直转圈。"""
    from db import get_db
    with app.app_context():
        uid = get_db().execute("SELECT id FROM users WHERE username='tester'").fetchone()[0]
        get_db().execute(
            "INSERT INTO ai_jobs (user_id, kind, status) VALUES (?, 't_quick', 'running')",
            (uid,))
        get_db().commit()
        assert ai_jobs.cleanup_orphans() >= 1
    rows = auth_client.get("/api/ai-jobs").get_json()
    assert rows[0]["status"] == "failed" and "重启" in rows[0]["error"]
