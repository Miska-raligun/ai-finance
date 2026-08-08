"""验证统计端点缓存命中 + 写操作触发失效。"""
from constants import PARAM_AMOUNT, PARAM_CATEGORY, PARAM_DATE


def test_stats_monthly_cached_then_invalidated(app, auth_client):
    from cache import clear_all
    clear_all()

    # 第一次请求：空数据
    r1 = auth_client.get("/api/stats/monthly")
    assert r1.status_code == 200
    assert r1.get_json() == []

    # 通过 handler 写入一条记录（触发 invalidate_user）
    from handlers import add_record
    with app.app_context():
        add_record(
            session_uid(auth_client),
            {PARAM_CATEGORY: "餐饮", PARAM_AMOUNT: 50, PARAM_DATE: "2025-04-01"},
        )

    # 再请求应能看到新数据
    r2 = auth_client.get("/api/stats/monthly")
    assert r2.status_code == 200
    body = r2.get_json()
    assert any(row["month"] == "2025-04" for row in body), body


def session_uid(client):
    with client.session_transaction() as s:
        return s["user_id"]
