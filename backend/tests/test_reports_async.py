"""异步月报：generate 立即返回 pending → 后台线程 → 轮询 status。"""
import time

import pytest


def _seed_minimum_record(app, uid, period="2025-04"):
    from db import get_db
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO records (user_id, category, amount, date) VALUES (?, ?, ?, ?)",
            (uid, "餐饮", 12.5, f"{period}-15"),
        )
        db.execute(
            "INSERT INTO categories (user_id, name, type) VALUES (?, ?, ?)",
            (uid, "餐饮", "支出"),
        )
        db.commit()


@pytest.fixture
def patched_llm(monkeypatch):
    """把 call_llm_monthly_report 替换为快速返回，避免真打外部 LLM。"""
    import services.reports as reports_mod

    def _fake(insights, llm=None):
        time.sleep(0.05)
        return f"# {insights['period']} 月度报告\n\n## 概览\n本月净结余 ¥0。"

    # 覆盖 services.llm 中的引用（通过 service.reports 的 import 链替换为快速路径）
    import services.llm as llm_mod
    monkeypatch.setattr(llm_mod, "call_llm_monthly_report", _fake)
    return _fake


def test_generate_no_data_returns_done_immediately(auth_client, app):
    """该月无任何数据时直接落库为 done，不走 LLM 也不需要轮询。"""
    with auth_client.session_transaction() as s:
        uid = s["user_id"]

    r = auth_client.post("/api/reports/generate?month=2099-12", json={})
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "done"
    assert "无任何记录" in body["content"]


def test_generate_async_then_poll_to_done(auth_client, app, patched_llm):
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    _seed_minimum_record(app, uid, "2025-04")

    # POST 立即返回 pending（0.05s sleep 比 HTTP 响应慢一点已经足够触发 pending）
    r = auth_client.post("/api/reports/generate?month=2025-04", json={})
    assert r.status_code == 200
    body = r.get_json()
    assert body["period"] == "2025-04"
    assert body["status"] in ("pending", "done")  # 后台线程极快时可能已 done

    # 轮询直到 done
    deadline = time.time() + 5
    final_status = None
    while time.time() < deadline:
        rr = auth_client.get("/api/reports/2025-04/status")
        assert rr.status_code == 200
        final_status = rr.get_json()["status"]
        if final_status == "done":
            break
        time.sleep(0.1)
    assert final_status == "done", f"期望 done，最终 {final_status}"

    # 拿详情验证 content
    detail = auth_client.get("/api/reports/2025-04")
    assert detail.status_code == 200
    assert "月度报告" in detail.get_json()["content"]


def test_status_404_for_unknown_period(auth_client):
    r = auth_client.get("/api/reports/2099-01/status")
    assert r.status_code == 404
