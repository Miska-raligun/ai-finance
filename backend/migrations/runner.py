"""迁移执行器：扫描同目录下 NNNN_*.sql / NNNN_*.py，依据 schema_version 表幂等执行。

.py 迁移用于 .sql 干不了的活——典型是要按业务规则重写 JSON 列(SQLite 的
JSON1 能做,但写出来没人看得懂)。它必须定义 `migrate(conn)`，提交由执行器负责。
"""
from __future__ import annotations

import importlib.util
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
    for pattern in ("[0-9]*.sql", "[0-9]*.py"):
        for path in _MIGRATIONS_DIR.glob(pattern):
            try:
                version = int(path.stem.split("_", 1)[0])
            except ValueError:
                logger.warning("跳过无法解析版本号的迁移文件：%s", path.name)
                continue
            files.append((version, path))
    files.sort(key=lambda x: x[0])
    return files


def _run_py_migration(conn: sqlite3.Connection, path: Path) -> None:
    """按路径加载并执行,不走 import 机制——迁移文件不是包的一部分,
    也不该被别处 import 到。"""
    spec = importlib.util.spec_from_file_location(f"_migration_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "migrate"):
        raise RuntimeError(f"迁移 {path.name} 没有定义 migrate(conn)")
    mod.migrate(conn)


def apply_migrations(conn: sqlite3.Connection) -> list[int]:
    """按版本号顺序应用未执行的迁移，返回本次新执行的版本号列表。"""
    _ensure_version_table(conn)
    applied = _applied_versions(conn)
    newly_applied: list[int] = []

    for version, path in _discover_migrations():
        if version in applied:
            continue
        try:
            if path.suffix == ".py":
                _run_py_migration(conn, path)
            else:
                conn.executescript(path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_version (version, name, applied_at) VALUES (?, ?, ?)",
                (version, path.name, datetime.utcnow().isoformat(timespec="seconds")),
            )
            conn.commit()
            newly_applied.append(version)
            logger.info("已应用迁移 %s", path.name)
        except Exception as e:  # noqa: BLE001  .py 迁移抛什么都可能
            conn.rollback()
            logger.error("迁移 %s 失败：%s", path.name, e)
            raise

    return newly_applied
