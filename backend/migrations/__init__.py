"""SQLite 迁移系统：按版本号顺序执行 .sql 文件并记录到 schema_version。"""
from .runner import apply_migrations

__all__ = ["apply_migrations"]
