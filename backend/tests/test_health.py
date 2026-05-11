"""/api/heartbeat 健康检查端点。

属于 CSRF 豁免名单，无需登录、无需 token 即可调用。"""


def test_heartbeat_basic_ok(client):
    r = client.get("/api/heartbeat")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] in ("ok", "degraded")
    assert "version" in body
    assert "uptime_sec" in body and body["uptime_sec"] >= 0
    assert body["db_ok"] is True
    assert body["timestamp"].endswith("Z")


def test_heartbeat_no_auth_required(client):
    """不要把 login_required 加到 heartbeat 上，否则负载均衡探活会一直 401。"""
    r = client.get("/api/heartbeat")
    assert r.status_code == 200, "heartbeat must be reachable without session"


def test_heartbeat_does_not_set_cookie(client):
    """探活请求不应留下 session / csrf cookie 痕迹（fixture app 没挂 csrf，正好检查）。"""
    r = client.get("/api/heartbeat")
    # session cookie 不该被设置（fixture app 没注册 csrf，但万一 set-cookie 来自其它地方也警告一下）
    set_cookie = r.headers.get("Set-Cookie", "")
    assert "session=" not in set_cookie
