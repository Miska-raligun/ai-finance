"""收据图片落地 + 数据库注册。

存储约定：
  * 物理文件：backend/uploads/receipts/<sha256>.<ext>
  * sha256 内容寻址：相同图片只占一份磁盘
  * 仅在用户尚未关联时记 record_id=NULL；commit_record 成功后回填
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime

from db import get_db

logger = logging.getLogger(__name__)

# 相对 backend/ 的路径
_UPLOAD_BASE = os.path.join(os.path.dirname(__file__), "..", "uploads", "receipts")

_EXT_BY_MIME = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def _ensure_dir() -> None:
    os.makedirs(_UPLOAD_BASE, exist_ok=True)


def store_receipt(user_id: int, image_bytes: bytes, mime: str) -> dict:
    """落盘 + 注册到 receipts 表。返回 {id, sha256, path, deduped}。"""
    if mime not in _EXT_BY_MIME:
        raise ValueError(f"不支持的图片格式：{mime}")
    if not image_bytes:
        raise ValueError("空图片")

    _ensure_dir()
    sha = hashlib.sha256(image_bytes).hexdigest()
    ext = _EXT_BY_MIME[mime]
    rel_path = f"uploads/receipts/{sha}.{ext}"
    abs_path = os.path.join(os.path.dirname(__file__), "..", rel_path)

    # 内容寻址 dedup：相同 sha 复用磁盘文件
    if not os.path.exists(abs_path):
        with open(abs_path, "wb") as f:
            f.write(image_bytes)

    db = get_db()
    row = db.execute(
        "SELECT id, path FROM receipts WHERE user_id = ? AND sha256 = ?",
        (user_id, sha),
    ).fetchone()
    if row:
        return {"id": row["id"], "sha256": sha, "path": row["path"], "deduped": True}

    cur = db.execute(
        "INSERT INTO receipts (user_id, mime, sha256, bytes, path, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, mime, sha, len(image_bytes), rel_path,
         datetime.utcnow().isoformat(timespec="seconds")),
    )
    db.commit()
    return {"id": cur.lastrowid, "sha256": sha, "path": rel_path, "deduped": False}


def attach_to_record(user_id: int, receipt_id: int, *, record_id: int, kind: str) -> bool:
    """记账确认后把图片关联到具体 record / income 行。返回是否更新成功。"""
    if kind not in ("expense", "income"):
        return False
    db = get_db()
    res = db.execute(
        "UPDATE receipts SET record_id = ?, record_kind = ? "
        "WHERE id = ? AND user_id = ? AND record_id IS NULL",
        (record_id, kind, receipt_id, user_id),
    )
    db.commit()
    return res.rowcount > 0


def get_receipt(user_id: int, receipt_id: int) -> dict | None:
    row = get_db().execute(
        "SELECT id, mime, sha256, bytes, path, record_id, record_kind, created_at "
        "FROM receipts WHERE id = ? AND user_id = ?",
        (receipt_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def absolute_path(rel_path: str) -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", rel_path))
