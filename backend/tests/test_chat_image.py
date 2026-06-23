"""chat_image:MiniMax MCP 不可达 / 识别失败时,接口仍要返回 200 而非 500,
且 receipt 已归档(图片本体不丢)。"""
from __future__ import annotations

import io

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


def test_chat_image_ocr_failure_returns_200_with_fallback(chat_client, monkeypatch):
    """OCR 返回 None(MiniMax 不可达 / 识别失败)时,路由应返回 200 + 友好提示,
    而不是抛 500;同时 receipt 应已归档(receipt_id 不为 None)。"""
    monkeypatch.setattr("routes.chat.recognize_image", lambda b64, mime: None)

    r = chat_client.post(
        "/api/chat/image",
        data={"image": (io.BytesIO(_png_bytes()), "bill.png", "image/png")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    body = r.get_json()
    assert "识别失败" in body["reply"]
    assert body["pending_records"] == []
    # 即便 OCR 挂了,小票归档应已落地,前端可关联到手填记录
    assert body.get("receipt_id") is not None
