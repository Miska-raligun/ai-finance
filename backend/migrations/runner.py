"""迁移执行器：扫描同目录下 NNNN_*.sql，依据 schema_version 表幂等执行。"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).parent


def _ensure_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            name TEXT,
            applied_at TEXT
        )
        """
    )
    conn.commit()


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    rows = conn.execute("SELECT version FROM schema_version").fetchall()
    return {int(r[0]) for r in rows}


def _discover_migrations() -> list[tuple[int, Path]]:
    files = []
    for path in _MIGRATIONS_DIR.glob("[0-9]*.sql"):
        try:
            version = int(path.stem.split("_", 1)[0])
        except ValueError:
            logger.warning("跳过无法解析版本号的迁移文件：%s", path.name)
            continue
        files.append((version, path))
    files.sort(key=lambda x: x[0])
    return files


def apply_migrations(conn: sqlite3.Connection) -> list[int]:
    """按版本号顺序应用未执行的迁移，返回本次新执行的版本号列表。"""
    _ensure_version_table(conn)
    applied = _applied_versions(conn)
    newly_applied: list[int] = []

    for version, path in _discover_migrations():
        if version in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_version (version, name, applied_at) VALUES (?, ?, ?)",
                (version, path.name, datetime.utcnow().isoformat(timespec="seconds")),
            )
            conn.commit()
            newly_applied.append(version)
            logger.info("已应用迁移 %s", path.name)
        except sqlite3.Error as e:
            conn.rollback()
            logger.error("迁移 %s 失败：%s", path.name, e)
            raise

    return newly_applied
