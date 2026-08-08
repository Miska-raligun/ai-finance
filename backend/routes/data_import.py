"""数据导入:回灌导出的 records / income(CSV / JSON)。

配套 export.py——换设备 / 迁移时把导出的文件导回来。按 (date, amount, note)
去重,重复行跳过,不覆盖已有数据。分类不存在时自动补建(与手动记账一致)。
"""
from __future__ import annotations

import csv
import io
import json

from flask import Blueprint, g, jsonify, request

from auth import login_required
from cache import invalidate_user
from constants import CATEGORY_EXPENSE, CATEGORY_INCOME
from db import get_db

import_bp = Blueprint("data_import", __name__)

_MAX_ROWS = 20000            # 单次导入行数上限,防超大文件打爆内存
_MAX_BYTES = 8 * 1024 * 1024  # 8MB

# 导出表头 → 内部字段。兼容 records(分类)与 income(来源)两种表头。
_HEADER_ALIASES = {
    "日期": "date", "date": "date",
    "分类": "category", "来源": "category", "category": "category",
    "金额": "amount", "amount": "amount",
    "备注": "note", "note": "note",
}


def _norm_row(raw: dict) -> dict | None:
    """把一行(表头已归一)转成 {date, category, amount, note};非法行返回 None。"""
    date = (raw.get("date") or "").strip()[:10]
    category = (raw.get("category") or "").strip()
    note = (raw.get("note") or "").strip()
    try:
        amount = round(float(raw.get("amount") or 0), 2)
    except (TypeError, ValueError):
        return None
    if not date or len(date) != 10 or amount <= 0 or not category:
        return None
    return {"date": date, "category": category, "amount": amount, "note": note}


def _parse_payload(kind: str, content: bytes, fmt: str) -> list[dict]:
    text = content.decode("utf-8-sig", errors="replace")
    rows: list[dict] = []
    if fmt == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 解析失败:{e}") from e
        if isinstance(data, dict):
            data = data.get("data") or data.get(kind) or []
        if not isinstance(data, list):
            raise ValueError("JSON 顶层应为数组或 {data:[...]}")
        raw_rows = data
    else:  # csv
        reader = csv.DictReader(io.StringIO(text))
        raw_rows = list(reader)

    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        mapped = {}
        for k, v in raw.items():
            key = _HEADER_ALIASES.get((k or "").strip())
            if key:
                mapped[key] = v
        norm = _norm_row(mapped)
        if norm:
            rows.append(norm)
        if len(rows) > _MAX_ROWS:
            raise ValueError(f"超过单次导入上限 {_MAX_ROWS} 行,请拆分文件")
    return rows


@import_bp.route("/api/import", methods=["POST"])
@login_required
def import_data():
    """multipart:file + type(records|income)+ format(csv|json,可省,按扩展名猜)。
    返回 {imported, skipped, invalid}。"""
    kind = (request.form.get("type") or "records").strip()
    if kind not in ("records", "income"):
        return jsonify({"error": "type 仅支持 records / income"}), 400
    if "file" not in request.files:
        return jsonify({"error": "未收到文件"}), 400

    f = request.files["file"]
    content = f.read()
    if len(content) > _MAX_BYTES:
        return jsonify({"error": "文件超过 8MB"}), 400

    fmt = (request.form.get("format") or "").strip().lower()
    if not fmt:
        fmt = "json" if (f.filename or "").lower().endswith(".json") else "csv"

    try:
        rows = _parse_payload(kind, content, fmt)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if not rows:
        return jsonify({"imported": 0, "skipped": 0, "invalid": 0,
                        "message": "没有可导入的有效行(检查表头:日期/分类/金额/备注)"})

    table = "records" if kind == "records" else "income"
    cat_type = CATEGORY_EXPENSE if kind == "records" else CATEGORY_INCOME
    db = get_db()

    # 已有 (date, amount, note) 集合,用于去重(含软删行,避免导入把删掉的又灌回来)
    existing = {
        (r["date"], round(float(r["amount"]), 2), r["note"] or "")
        for r in db.execute(
            f"SELECT date, amount, note FROM {table} WHERE user_id = ?", (g.user_id,)
        ).fetchall()
    }
    known_cats = {
        r["name"] for r in db.execute(
            "SELECT name FROM categories WHERE user_id = ? AND type = ?",
            (g.user_id, cat_type),
        ).fetchall()
    }

    imported = skipped = 0
    for r in rows:
        key = (r["date"], r["amount"], r["note"])
        if key in existing:
            skipped += 1
            continue
        if r["category"] not in known_cats:
            db.execute("INSERT OR IGNORE INTO categories (user_id, name, type) VALUES (?, ?, ?)",
                       (g.user_id, r["category"], cat_type))
            known_cats.add(r["category"])
        db.execute(
            f"INSERT INTO {table} (user_id, category, amount, note, date) VALUES (?, ?, ?, ?, ?)",
            (g.user_id, r["category"], r["amount"], r["note"], r["date"]),
        )
        existing.add(key)
        imported += 1

    db.commit()
    invalidate_user(g.user_id)
    return jsonify({
        "imported": imported,
        "skipped": skipped,
        "invalid": len(rows) and 0,  # _parse 已过滤非法行
        "message": f"导入 {imported} 条,跳过 {skipped} 条重复",
    })
