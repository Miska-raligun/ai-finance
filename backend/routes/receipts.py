"""收据图片访问路由：列出当前用户所有收据 + 通过 ID 取图片字节。"""
from __future__ import annotations

import os

from flask import Blueprint, g, jsonify, send_file, abort

from auth import login_required

receipts_bp = Blueprint("receipts", __name__)


@receipts_bp.route("/api/receipts", methods=["GET"])
@login_required
def list_receipts():
    """最近的收据列表，用于"我的票据"页或调试。"""
    from db import get_db
    rows = get_db().execute(
        "SELECT id, mime, sha256, bytes, record_id, record_kind, created_at "
        "FROM receipts WHERE user_id = ? ORDER BY id DESC LIMIT 100",
        (g.user_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@receipts_bp.route("/api/receipts/<int:receipt_id>", methods=["GET"])
@login_required
def get_receipt_image(receipt_id: int):
    """以原 mime 流式返回图片字节。"""
    from services.receipts import get_receipt, absolute_path
    info = get_receipt(g.user_id, receipt_id)
    if not info:
        abort(404, description="收据不存在")
    full = absolute_path(info["path"])
    if not os.path.isfile(full):
        abort(410, description="图片文件已丢失")
    return send_file(full, mimetype=info["mime"],
                     download_name=f"receipt-{info['sha256'][:8]}." + info["mime"].split("/")[-1])


@receipts_bp.route("/api/receipts/<int:receipt_id>", methods=["DELETE"])
@login_required
def delete_receipt(receipt_id: int):
    """删除一条收据。物理文件若被其他记录引用则保留（按 sha256 dedup）。"""
    from db import get_db
    from services.receipts import get_receipt, absolute_path

    info = get_receipt(g.user_id, receipt_id)
    if not info:
        return jsonify({"error": "不存在"}), 404
    db = get_db()
    db.execute("DELETE FROM receipts WHERE id = ? AND user_id = ?",
               (receipt_id, g.user_id))
    db.commit()
    # 若同 sha 已无引用，再删物理文件
    other = db.execute(
        "SELECT COUNT(*) FROM receipts WHERE sha256 = ?",
        (info["sha256"],),
    ).fetchone()[0]
    if other == 0:
        try:
            os.remove(absolute_path(info["path"]))
        except OSError:
            pass
    return jsonify({"success": True})
