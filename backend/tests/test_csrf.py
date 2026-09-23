"""CSRF 双重提交校验：cookie + header 必须同值。

同时验证响应头镜像 token 的能力——前端不必依赖 vite proxy 透传 Set-Cookie。
"""
import os
import pytest


@pytest.fixture
def csrf_app(monkeypatch, app):
    """打开 CSRF 校验后再返回 app（默认 fixture 不挂 csrf）。"""
    monkeypatch.setenv("SECRET_KEY", "x" * 64)
    from csrf import register_csrf
    register_csrf(app)
    return app


@pytest.fixture
def csrf_client(csrf_app):
    return csrf_app.test_client()


def test_get_response_includes_csrf_header(csrf_client):
    """每次响应都把 token 镜像到 X-CSRF-Token 头，规避 Set-Cookie 透传问题。"""
    r = csrf_client.get("/api/me")  # 会 401 但应包含 CSRF 头与 cookie
    token = r.headers.get("X-CSRF-Token")
    assert token, "X-CSRF-Token 响应头必须始终存在"


def test_post_without_token_rejected(csrf_client, auth_client):
    # auth_client fixture 把 user_id 写进 session；用其复用 session
    with auth_client.session_transaction() as src:
        sess = dict(src)
    with csrf_client.session_transaction() as dst:
        dst.update(sess)

    r = csrf_client.post("/api/records", json={"category": "x", "amount": 1})
    assert r.status_code == 403
    body = r.get_json()
    assert body["error"] == "CSRFRejected"


def test_post_with_matching_token_passes(csrf_client, auth_client):
    """先 GET 拿 token，再 POST 同时带 cookie + header 应放行。"""
    with auth_client.session_transaction() as src:
        sess = dict(src)
    with csrf_client.session_transaction() as dst:
        dst.update(sess)

    g = csrf_client.get("/api/me")
    token = g.headers["X-CSRF-Token"]

    # test client 自动复用 GET 响应中 set 的 cookie
    r = csrf_client.post(
        "/api/records",
        json={"category": "餐饮", "amount": 12.5, "date": "2025-04-01"},
        headers={"X-CSRF-Token": token},
    )
    # 不关心业务返回 200 还是 400/422，只验证 CSRF 没拦
    assert r.status_code != 403, f"CSRF 应通过，实际返回 {r.status_code} {r.get_data(as_text=True)}"


def test_login_endpoint_exempt(csrf_client):
    """/api/login 必须能在不带 cookie 的情况下被调用，否则用户无法登录。"""
    r = csrf_client.post("/api/login", json={"username": "x", "password": "y"})
    # 用户名错就 400，不会因 CSRF 被 403
    assert r.status_code != 403


def test_token_remains_stable_within_session(csrf_client):
    """同一个 client 的多次请求应当共用一个 token，避免 token 轮转后旧的失效。"""
    r1 = csrf_client.get("/api/me")
    r2 = csrf_client.get("/api/me")
    assert r1.headers["X-CSRF-Token"] == r2.headers["X-CSRF-Token"]
