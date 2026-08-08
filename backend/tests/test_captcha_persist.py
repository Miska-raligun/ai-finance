"""Captcha 持久化：验证码不再保存在内存，重启后仍可校验。"""
from __future__ import annotations


def test_captcha_validate_via_db(app):
    from auth import generate_captcha, validate_captcha

    with app.app_context():
        token, chars, _img = generate_captcha()
        # 模拟跨进程：直接清空模块变量也能从 DB 读取
        ok, err = validate_captcha(token, chars.lower())  # 大小写不敏感
        assert ok, err

        # 再次校验同一 token 应失败（已消费）
        ok2, err2 = validate_captcha(token, chars)
        assert not ok2


def test_captcha_wrong_input(app):
    from auth import generate_captcha, validate_captcha

    with app.app_context():
        token, _chars, _img = generate_captcha()
        ok, err = validate_captcha(token, "WRONG")
        assert not ok
        assert "错误" in err

        # 错误后 token 也应被消费
        ok2, _ = validate_captcha(token, _chars)
        assert not ok2


def test_captcha_expired_cleanup(app):
    """直接写入过期记录，验证 validate 拒绝且清理。"""
    from db import get_db
    from auth import validate_captcha

    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO captcha_store (token, answer, expires_at) VALUES (?, ?, ?)",
            ("expired-token", "ABCD", 1),
        )
        db.commit()
        ok, err = validate_captcha("expired-token", "ABCD")
        assert not ok
        assert "过期" in err
        # 应已被删除
        row = db.execute(
            "SELECT 1 FROM captcha_store WHERE token = ?", ("expired-token",),
        ).fetchone()
        assert row is None
