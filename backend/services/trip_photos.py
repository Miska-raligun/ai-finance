"""行程景点照片:落盘 + 注册。

存储约定与收据一致:
  * 物理文件:backend/uploads/trips/<sha256>.<ext>
  * 只存一份显示尺寸(长边 800px)的图,不留原图,见 to_display
  * sha256 内容寻址,同一张图只占一份磁盘
  * 停留点在 detail_json 里只记 sha,不记 URL——私有页和公开分享页的
    URL 前缀不同,存死了分享出去就取不到
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
from datetime import datetime

from db import get_db

_UPLOAD_BASE = os.path.join(os.path.dirname(__file__), "..", "uploads", "trips")

_EXT_BY_MIME = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

# 服务端只留"够显示用"的那一份,不留原图:长边 800px 的 JPEG,正常照片
# 一张一两百 KB 以内。前端上传前就缩到这个尺寸(utils/tripPhotos.js 的
# DISPLAY_MAX,两边要一致);这里再兜一次底,防止旧页面或直接打接口传大图。
DISPLAY_MAX = 800
JPEG_QUALITY = 75
MAX_STORED_BYTES = 300 * 1024
# 接收上限放宽些:没刷新的旧页面还会传 1280px 的图,收下来再缩
MAX_BYTES = 4 * 1024 * 1024

logger = logging.getLogger(__name__)


def to_display(image_bytes: bytes, mime: str) -> tuple[bytes, str]:
    """尺寸或体积超标、或带 EXIF(可能有 GPS)的,重新编码成显示尺寸的 JPEG;
    本来就合格的原样返回,免得二次压缩掉画质。没装 Pillow 就原样返回。"""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        logger.warning("未安装 Pillow,照片不做服务端缩图(pip install Pillow)")
        return image_bytes, mime
    try:
        im = Image.open(io.BytesIO(image_bytes))
        fits = (max(im.size) <= DISPLAY_MAX and len(image_bytes) <= MAX_STORED_BYTES
                and not im.info.get("exif"))
        if fits:
            return image_bytes, mime
        im.draft("RGB", (DISPLAY_MAX, DISPLAY_MAX))   # JPEG 直接按缩小的尺寸解码,快很多
        im = ImageOps.exif_transpose(im)
        im.thumbnail((DISPLAY_MAX, DISPLAY_MAX))
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        elif im.mode != "RGB":
            im = im.convert("RGB")
        out = io.BytesIO()
        im.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
        return out.getvalue(), "image/jpeg"
    except Exception as e:  # noqa: BLE001  Pillow 解不开的各种坏图
        raise ValueError("图片无法解析") from e


def store_photo(user_id: int, trip_id: int, image_bytes: bytes, mime: str) -> dict:
    if mime not in _EXT_BY_MIME:
        raise ValueError("只支持 JPEG / PNG / WebP")
    if not image_bytes:
        raise ValueError("空图片")
    if len(image_bytes) > MAX_BYTES:
        raise ValueError("图片太大(超过 4MB)")
    image_bytes, mime = to_display(image_bytes, mime)

    os.makedirs(_UPLOAD_BASE, exist_ok=True)
    sha = hashlib.sha256(image_bytes).hexdigest()
    rel_path = f"uploads/trips/{sha}.{_EXT_BY_MIME[mime]}"
    abs_path = absolute_path(rel_path)
    if not os.path.exists(abs_path):
        with open(abs_path, "wb") as f:
            f.write(image_bytes)

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


def _legacy_thumb_path(rel_path: str) -> str:
    """上一版另存的缩略图 <sha>_t.jpg。现在只存一份显示尺寸的图,
    这个文件只在收尾和清理旧数据时用来删掉。"""
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
            for p in (absolute_path(r["path"]), _legacy_thumb_path(r["path"])):
                try:
                    os.remove(p)
                except OSError:
                    pass
    if removed:
        db.commit()
    return removed


def shrink_existing_photos() -> int:
    """把之前存下的大图就地缩成显示尺寸,顺手删掉上一版另存的缩略图。

    启动时跑一次,尽力而为:幂等(已经合格的只读一下文件头),单张失败
    跳过不影响其他。sha 只是照片的编号,内容变了也照用——停留点里记的
    还是它,文件名也不变,所以已有链接全都有效。返回缩了几张。
    """
    db = get_db()
    paths = [r[0] for r in db.execute("SELECT DISTINCT path FROM trip_photos").fetchall()]
    shrunk = 0
    for rel in paths:
        try:
            os.remove(_legacy_thumb_path(rel))
        except OSError:
            pass
        full = absolute_path(rel)
        try:
            with open(full, "rb") as f:
                raw = f.read()
            row = db.execute("SELECT mime FROM trip_photos WHERE path = ? LIMIT 1", (rel,)).fetchone()
            out, mime = to_display(raw, row[0])
        except (OSError, ValueError):
            continue
        if out is raw:
            continue
        tmp = full + ".tmp"
        with open(tmp, "wb") as f:
            f.write(out)
        os.replace(tmp, full)            # 原子替换:正在读这张图的请求不会读到半截
        db.execute("UPDATE trip_photos SET mime = ?, bytes = ? WHERE path = ?", (mime, len(out), rel))
        shrunk += 1
    if shrunk:
        db.commit()
        logger.info("行程照片:%d 张旧图已缩成显示尺寸", shrunk)
    return shrunk
