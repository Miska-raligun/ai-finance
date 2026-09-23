"""rate_limit:apply_endpoint_limits 装上后超频请求应得 429,响应体走自定义
handler 而非 Flask 默认 HTML 错误页。"""
from __future__ import annotations

import pytest


@pytest.fixture
def limited_app(app):
    """给 health.heartbeat 临时套一个紧规则,便于快速触发 429。
    选 heartbeat 是因为它不依赖外部资源、命中后无副作用。"""
    from rate_limit import apply_endpoint_limits, limiter

    if limiter is None:
        pytest.skip("flask-limiter 未安装,跳过限流测试")

    apply_endpoint_limits(app, {"health.heartbeat": "2/minute"})
    yield app


def test_rate_limit_triggers_429_after_threshold(limited_app):
    """连续命中超出 2/minute 配额后第 3 次应返回 429,JSON 体里带自定义字段。"""
    client = limited_app.test_client()
    assert client.get("/api/heartbeat").status_code == 200
    assert client.get("/api/heartbeat").status_code == 200

    r = client.get("/api/heartbeat")
    assert r.status_code == 429
    body = r.get_json()
    assert body["error"] == "RateLimitExceeded"
    assert body["code"] == 429
    assert "message" in body
