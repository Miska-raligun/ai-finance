"""LLM 每日 token 配额并发竞态：两个同时请求不应同时越线。

旧实现是「读 SUM 检查」与「事后 INSERT」分两个事务，并发下都能读到 99/100 都过检查
再都 INSERT。新实现 `_reserve_quota_slot` 用 SQLite BEGIN IMMEDIATE 串行化「读+写占位」，
本测试确认第二个请求会被 quota 拦下。
"""
from datetime import datetime


def _seed_used_tokens(app, uid, used: int):
    """直接写一行已用 token 进 llm_usage，把当日 SUM 顶到 used。"""
    from db import get_db
    today = datetime.utcnow().isoformat(timespec="seconds")
    with app.app_context():
        db = get_db()
        db.execute(
            """INSERT INTO llm_usage
               (user_id, endpoint, model, prompt_tokens, completion_tokens,
                total_tokens, cost_usd, request_id, created_at, latency_ms,
                status, error_reason, provider)
               VALUES (?, 'seed', 'm', 0, ?, ?, 0, NULL, ?, 0,
                       'success', NULL, 'openai')""",
            (uid, used, used, today),
        )
        db.commit()


def test_quota_reserve_blocks_when_exceeded(auth_client, app, monkeypatch):
    """额度已用 = 上限时，预占函数抛 LLMQuotaExceeded。"""
    monkeypatch.setenv("LLM_DAILY_TOKEN_LIMIT", "100")
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    _seed_used_tokens(app, uid, 100)

    from services.llm import _reserve_quota_slot, LLMQuotaExceeded
    with app.test_request_context():
        from flask import g
        g.user_id = uid
        try:
            _reserve_quota_slot("test", "m", "openai")
            assert False, "应该抛 LLMQuotaExceeded"
        except LLMQuotaExceeded:
            pass


def test_quota_reserve_creates_pending_slot(auth_client, app, monkeypatch):
    """未达上限时，预占函数 INSERT 一行 status='pending' 占额度。"""
    monkeypatch.setenv("LLM_DAILY_TOKEN_LIMIT", "100")
    with auth_client.session_transaction() as s:
        uid = s["user_id"]

    from services.llm import _reserve_quota_slot
    with app.test_request_context():
        from flask import g
        g.user_id = uid
        slot_id = _reserve_quota_slot("test", "m", "openai")
        assert isinstance(slot_id, int) and slot_id > 0

        # 写完后再调一次（用了 0 token），还是该过
        slot2 = _reserve_quota_slot("test", "m", "openai")
        assert isinstance(slot2, int) and slot2 != slot_id

    # 验 DB：两行 pending、tokens=0
    from db import get_db
    with app.app_context():
        rows = get_db().execute(
            "SELECT status, total_tokens FROM llm_usage WHERE user_id=?",
            (uid,),
        ).fetchall()
        pendings = [r for r in rows if r["status"] == "pending"]
        assert len(pendings) == 2
        assert all(r["total_tokens"] == 0 for r in pendings)


def test_quota_pending_counts_toward_limit(auth_client, app, monkeypatch):
    """关键反竞态属性：占位 pending 行也应被 SUM 计入，防止第二个并发请求误以为还有额度。"""
    monkeypatch.setenv("LLM_DAILY_TOKEN_LIMIT", "100")
    with auth_client.session_transaction() as s:
        uid = s["user_id"]

    # 先手工塞一行 pending 占满上限（模拟「上一个请求刚预占完还没 finalize」的瞬间）
    from db import get_db
    from datetime import datetime as _dt
    now = _dt.utcnow().isoformat(timespec="seconds")
    with app.app_context():
        # pending 行本身 total_tokens=0，但只要再来一行 success 凑够上限就够。
        # 这里更严苛：直接放一行 status='pending', total_tokens=100。
        get_db().execute(
            """INSERT INTO llm_usage
               (user_id, endpoint, model, prompt_tokens, completion_tokens,
                total_tokens, cost_usd, request_id, created_at, latency_ms,
                status, error_reason, provider)
               VALUES (?, 'reserved', 'm', 0, 100, 100, 0, NULL, ?, 0,
                       'pending', NULL, 'openai')""",
            (uid, now),
        )
        get_db().commit()

    from services.llm import _reserve_quota_slot, LLMQuotaExceeded
    with app.test_request_context():
        from flask import g
        g.user_id = uid
        try:
            _reserve_quota_slot("test", "m", "openai")
            assert False, "占位 pending 行 100 token 应该让后续请求被拦下"
        except LLMQuotaExceeded:
            pass


def test_quota_disabled_returns_none(app):
    """配额未启用（LIMIT=0）时返回 None，调用方走旧 _record_usage 路径不破坏 MCP/无登录场景。"""
    import os
    os.environ.pop("LLM_DAILY_TOKEN_LIMIT", None)
    from services.llm import _reserve_quota_slot
    with app.test_request_context():
        # 即使没设 g.user_id 也不该抛
        assert _reserve_quota_slot("test", "m", "openai") is None
