"""行程景点照片:落盘 + 注册。

存储约定与收据一致:
  * 物理文件:backend/uploads/trips/<sha256>.<ext>
  * sha256 内容寻址,同一张图只占一份磁盘
  * 停留点在 detail_json 里只记 sha,不记 URL——私有页和公开分享页的
    URL 前缀不同,存死了分享出去就取不到
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

from db import get_db

_UPLOAD_BASE = os.path.join(os.path.dirname(__file__), "..", "uploads", "trips")

_EXT_BY_MIME = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

# 前端上传前会先缩到 1280px / JPEG,这里只是兜底,防止有人直接打接口
MAX_BYTES = 4 * 1024 * 1024
# 缩略图(480px JPEG)正常几十 KB
MAX_THUMB_BYTES = 512 * 1024


def store_photo(user_id: int, trip_id: int, image_bytes: bytes, mime: str,
                thumb: bytes | None = None) -> dict:
    if mime not in _EXT_BY_MIME:
        raise ValueError("只支持 JPEG / PNG / WebP")
    if not image_bytes:
        raise ValueError("空图片")
    if len(image_bytes) > MAX_BYTES:
        raise ValueError("图片太大(超过 4MB)")

    os.makedirs(_UPLOAD_BASE, exist_ok=True)
    sha = hashlib.sha256(image_bytes).hexdigest()
    rel_path = f"uploads/trips/{sha}.{_EXT_BY_MIME[mime]}"
    abs_path = absolute_path(rel_path)
    if not os.path.exists(abs_path):
        with open(abs_path, "wb") as f:
            f.write(image_bytes)
    # 缩略图跟原图共用 sha,只认 JPEG;不合格就当没传,取图时回落到原图
    if thumb and len(thumb) <= MAX_THUMB_BYTES and thumb[:3] == b"\xff\xd8\xff":
        tp = thumb_path(rel_path)
        if not os.path.exists(tp):
            with open(tp, "wb") as f:
                f.write(thumb)

    db = get_db()
    row = db.execute(
        "SELECT id FROM trip_photos WHERE trip_id = ? AND sha256 = ?", (trip_id, sha),
    ).fetchone()
    if row:
        return {"sha256": sha, "deduped": True}
    db.execute(
        "INSERT INTO trip_photos (trip_id, user_id, sha256, mime, bytes, path, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (trip_id, user_id, sha, mime, len(image_bytes), rel_path,
         datetime.now().isoformat(timespec="seconds")),
    )
    db.commit()
    return {"sha256": sha, "deduped": False}


def find_photo(trip_id: int, sha: str):
    """按 trip 校验归属再取。公开分享页也走这里——能不能看由分享 token 决定。"""
    if not sha or len(sha) != 64 or not all(c in "0123456789abcdef" for c in sha):
        return None
    row = get_db().execute(
        "SELECT mime, path FROM trip_photos WHERE trip_id = ? AND sha256 = ?", (trip_id, sha),
    ).fetchone()
    return dict(row) if row else None


def absolute_path(rel_path: str) -> str:
    # 库里记的是 uploads/trips/<文件名>,实际目录一律以 _UPLOAD_BASE 为准——
    # 写入和读取都走这里,目录改了(比如测试里指到临时目录)两边才对得上
    return os.path.normpath(os.path.join(_UPLOAD_BASE, os.path.basename(rel_path)))


def thumb_path(rel_path: str) -> str:
    """原图旁边的缩略图:<sha>.jpg → <sha>_t.jpg(缩略图一律是 JPEG)。"""
    stem = os.path.splitext(os.path.basename(rel_path))[0]
    return os.path.normpath(os.path.join(_UPLOAD_BASE, f"{stem}_t.jpg"))


def gc_trip_photos(trip_id: int) -> int:
    """清掉这趟行程里已经没人引用的照片。

    从界面上移掉一张照片,只是把 sha 从 detail_json 里去掉;不收尾的话
    文件和记录会一直留着,而且拿着旧链接还能取到——对个人照片来说,
    "删了就该是删了"。所以每次改完某天的 detail 就扫一遍这趟行程。

    物理文件按 sha 去重共享,只有在**所有**行程都不再引用时才删。
    """
    db = get_db()
    used: set[str] = set()
    for row in db.execute(
        "SELECT detail_json FROM trip_days WHERE trip_id = ?", (trip_id,),
    ).fetchall():
        try:
            detail = json.loads(row["detail_json"] or "{}")
        except (TypeError, ValueError):
            continue
        for stop in (detail.get("stops") or []):
            if not isinstance(stop, dict):
                continue
            photos = stop.get("photos")
            if isinstance(photos, list):
                used.update(p for p in photos if isinstance(p, str))
            elif isinstance(stop.get("photo"), str):
                used.add(stop["photo"])

    rows = db.execute(
        "SELECT id, sha256, path FROM trip_photos WHERE trip_id = ?", (trip_id,),
    ).fetchall()
    removed = 0
    for r in rows:
        if r["sha256"] in used:
            continue
        db.execute("DELETE FROM trip_photos WHERE id = ?", (r["id"],))
        removed += 1
        others = db.execute(
            "SELECT COUNT(*) FROM trip_photos WHERE sha256 = ?", (r["sha256"],),
        ).fetchone()[0]
        if others == 0:
            for p in (absolute_path(r["path"]), thumb_path(r["path"])):
                try:
                    os.remove(p)
                except OSError:
                    pass
    if removed:
        db.commit()
    return removed
