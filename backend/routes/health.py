"""健康检查 + 系统信息端点。

供反向代理 / 监控探针 / 部署后 smoke test 使用。CSRF middleware 已把
/api/heartbeat 列入豁免名单（csrf.py），所以可以匿名调用。
"""
from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime

from flask import Blueprint, jsonify

from db import get_db

health_bp = Blueprint("health", __name__)

# 进程启动时刻，用于 uptime 显示
_START_TIME = time.time()


@health_bp.route("/api/heartbeat", methods=["GET"])
def heartbeat():
    """轻量探活：500ms 内必返；不依赖外部服务（LLM / 行情）。

    返回字段：
      status        ok / degraded（DB 出错时 degraded，但仍 200，让 LB 不立刻摘流量）
      version       commit short hash（若存在 .git/HEAD）
      uptime_sec    进程已运行秒数
      db_ok         True/False；SELECT 1 是否成功
      timestamp     ISO8601 当前服务器时间
    """
    db_ok = True
    try:
        get_db().execute("SELECT 1").fetchone()
    except sqlite3.Error:
        db_ok = False

    return jsonify({
        "status": "ok" if db_ok else "degraded",
        "version": _read_version(),
        "uptime_sec": int(time.time() - _START_TIME),
        "db_ok": db_ok,
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    })


def _read_version() -> str:
    """读取 .git/HEAD 解析当前 commit short SHA；非 git 仓库或读不到时返回 'unknown'。"""
    try:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        head_path = os.path.join(repo_root, ".git", "HEAD")
        if not os.path.isfile(head_path):
            return "unknown"
        with open(head_path, encoding="utf-8") as f:
            head = f.read().strip()
        if head.startswith("ref:"):
            ref_path = os.path.join(repo_root, ".git", head[5:].strip())
            if os.path.isfile(ref_path):
                with open(ref_path, encoding="utf-8") as f:
                    return f.read().strip()[:7]
        return head[:7]
    except OSError:
        return "unknown"
