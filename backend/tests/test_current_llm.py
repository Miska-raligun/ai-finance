"""current_llm 的系统默认语义:无用户 key 时 url/model 走 constants.py,
不被 llm_config 表里残留的旧 url/model 覆盖;有用户 key 时尊重其配置。"""
from __future__ import annotations

import pytest

from constants import DEFAULT_LLM_URL, DEFAULT_LLM_MODEL
from services.llm_config import current_llm, save_llm_config


def _uid(app):
    from db import get_db
    with app.app_context():
        return get_db().execute("SELECT id FROM users WHERE username='tester'").fetchone()[0]


def test_no_row_uses_constants(app, auth_client):
    """没有 llm_config 行 → 系统默认 = constants.py。"""
    uid = _uid(app)
    with app.app_context():
        from flask import g
        g.user_id = uid
        cfg = current_llm({})
    assert cfg["url"] == DEFAULT_LLM_URL
    assert cfg["model"] == DEFAULT_LLM_MODEL


def test_stale_row_without_key_does_not_override_constants(app, auth_client):
    """关键场景:表里残留旧 model(V3)但用户没自己的 key → 仍走 constants.py,
    不被旧 model 盖过。这正是「改了 constants.py 不生效」的根因。"""
    uid = _uid(app)
    with app.app_context():
        from flask import g
        g.user_id = uid
        save_llm_config(uid, url="https://old.example/v1/chat/completions",
                        apikey="", model="Pro/deepseek-ai/DeepSeek-V3",
                        persona="老配置", provider="openai")
        cfg = current_llm({})
    assert cfg["model"] == DEFAULT_LLM_MODEL          # 不是残留的 V3
    assert cfg["url"] == DEFAULT_LLM_URL              # 不是残留的 old.example
    assert cfg.get("persona") == "老配置"             # 个性化保留


def test_user_key_respected(app, auth_client):
    """用户配了自己的 key + 模型 → 尊重其选择,不套 constants.py。"""
    uid = _uid(app)
    with app.app_context():
        from flask import g
        g.user_id = uid
        save_llm_config(uid, url="https://my.endpoint/v1/chat/completions",
                        apikey="sk-my-real-key", model="my-custom-model",
                        persona="", provider="openai")
        cfg = current_llm({})
    assert cfg["apikey"] == "sk-my-real-key"
    assert cfg["model"] == "my-custom-model"
    assert cfg["url"] == "https://my.endpoint/v1/chat/completions"


def test_request_payload_key_wins(app, auth_client):
    """请求里临时带 key + 模型 → 最高优先级。"""
    uid = _uid(app)
    with app.app_context():
        from flask import g
        g.user_id = uid
        cfg = current_llm({"llm": {"apikey": "sk-req", "model": "req-model",
                                   "url": "https://req/v1/chat/completions"}})
    assert cfg["model"] == "req-model"
    assert cfg["url"] == "https://req/v1/chat/completions"
