"""chat_image(异步任务版):上传立即返回 task_id;OCR 失败时任务以 failed 收场
并携带用户可读的错误文案;receipt 在上传时就已归档。"""
from __future__ import annotations

import io
import time

import pytest


@pytest.fixture
def chat_app(app):
    """conftest 没注册 chat_bp(避免常规测试拉 MCP 依赖),这里单独挂上。"""
    from routes.chat import chat_bp
    app.register_blueprint(chat_bp)
    return app


@pytest.fixture
def chat_client(chat_app, auth_client):
    """复用 auth_client 的 session,但 client 必须从 chat_app 取(才有 chat 蓝图)。"""
    return auth_client


def _png_bytes() -> bytes:
    """最短合法 PNG(1×1 透明像素),够通过 MIME 校验和大小校验。"""
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\rIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def _poll_task(client, task_id, timeout=10.0):
    """轮询任务直到离开 pending,worker 在线程池里跑,给它最多 timeout 秒。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/chat/image/tasks/{task_id}")
        assert r.status_code == 200
        data = r.get_json()
        if data["status"] != "pending":
            return data
        time.sleep(0.1)
    pytest.fail("图片识别任务超时未完成")


def test_chat_image_rejects_missing_file(chat_client):
    r = chat_client.post("/api/chat/image")
    assert r.status_code == 400
    assert r.get_json()["success"] is False


def test_chat_image_rejects_bad_mime(chat_client):
    r = chat_client.post(
        "/api/chat/image",
        data={"image": (io.BytesIO(b"garbage"), "x.txt", "text/plain")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 400


def test_chat_image_returns_task_then_fails_gracefully(chat_client, monkeypatch):
    """OCR 失败(MiniMax 不可达)时:上传仍立即 202 + task_id + receipt_id,
    任务最终 failed 且带用户可读 error,而不是同步 500 或干等 30 秒。"""
    monkeypatch.setattr(
        "routes.chat.recognize_image",
        lambda b64, mime: (None, "无法连接图片识别服务（localhost:5002）。请检查 minimax-mcp 服务是否在运行。"),
    )

    r = chat_client.post(
        "/api/chat/image",
        data={"image": (io.BytesIO(_png_bytes()), "bill.png", "image/png")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 202
    body = r.get_json()
    assert body["status"] == "pending"
    assert body["task_id"]
    # 即便 OCR 挂了,小票归档应已落地
    assert body.get("receipt_id") is not None

    final = _poll_task(chat_client, body["task_id"])
    assert final["status"] == "failed"
    # 错误文案要能指路(连不上服务),而不是笼统的"识别失败"
    assert "无法连接" in final["error"]


def test_chat_image_task_is_user_scoped(chat_client, monkeypatch, app):
    """别人的 task_id 查不到——防止横向读取他人识别结果。"""
    monkeypatch.setattr("routes.chat.recognize_image",
                        lambda b64, mime: (None, "mock 失败"))
    r = chat_client.post(
        "/api/chat/image",
        data={"image": (io.BytesIO(_png_bytes()), "bill.png", "image/png")},
        content_type="multipart/form-data",
    )
    task_id = r.get_json()["task_id"]

    # 换一个用户的 session 再查
    from werkzeug.security import generate_password_hash
    from db import get_db
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO users (username, password, is_admin) VALUES (?, ?, 0)",
            ("other", generate_password_hash("pwd")),
        )
        db.commit()
        other_id = db.execute(
            "SELECT id FROM users WHERE username = 'other'"
        ).fetchone()[0]
    with chat_client.session_transaction() as s:
        s["user_id"] = other_id
        s["username"] = "other"

    r2 = chat_client.get(f"/api/chat/image/tasks/{task_id}")
    assert r2.status_code == 404
