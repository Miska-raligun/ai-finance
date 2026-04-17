"""路由层冒烟测试：未登录拒绝、登录后能查空数据、错误响应结构。"""


def test_unauthorized_rejected(client):
    r = client.get("/api/records")
    assert r.status_code == 401
    assert r.json["error"] == "Unauthorized"


def test_records_empty_after_login(auth_client):
    r = auth_client.get("/api/records")
    assert r.status_code == 200
    body = r.get_json()
    assert body == {"data": [], "total": 0, "page": 1, "limit": 50}


def test_stats_summary_zero(auth_client):
    r = auth_client.get("/api/stats/summary")
    assert r.status_code == 200
    body = r.get_json()
    assert body["总支出"] == 0
    assert body["总收入"] == 0


def test_request_id_in_response_header(auth_client):
    r = auth_client.get("/api/records")
    assert r.headers.get("X-Request-Id"), "X-Request-Id 头必须返回"


def test_error_payload_includes_request_id(client):
    r = client.get("/api/records")
    assert r.status_code == 401
    body = r.get_json()
    assert "request_id" in body
    assert body["code"] == 401


def test_admin_endpoint_blocks_non_admin(auth_client):
    r = auth_client.get("/api/users")
    assert r.status_code == 403
