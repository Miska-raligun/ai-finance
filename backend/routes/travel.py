"""旅行计划:行程本 CRUD + 每日安排 + 手记 + 打包清单。

与静态行程页的关键差异:手记 / 打包勾选存库而不是 localStorage,
换设备不丢、多端同步(原页面自己标注「只存在这台设备上」)。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request

from auth import login_required
from db import get_db

travel_bp = Blueprint("travel", __name__)

# 每趟旅行的主题色预设:前端按名字注入 CSS 变量作用域,外壳保持统一风格。
ACCENTS = {"glacier", "aurora", "ember", "sakura", "desert", "violet"}

_DATE_FMT = "%Y-%m-%d"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_date(s: str):
    return datetime.strptime(s, _DATE_FMT).date()


def _valid_date(s: str) -> bool:
    try:
        _parse_date(s)
        return True
    except (TypeError, ValueError):
        return False


def _own_trip(trip_id: int):
    """取当前用户的行程(未软删),不存在返回 None。"""
    return get_db().execute(
        "SELECT * FROM trips WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (trip_id, g.user_id),
    ).fetchone()


def _day_row_to_dict(r) -> dict:
    d = dict(r)
    raw = d.pop("detail_json", None)
    try:
        d["detail"] = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        d["detail"] = {}
    return d


# ---------- 行程本 ----------

@travel_bp.route("/api/trips", methods=["GET"])
@login_required
def list_trips():
    """行程列表(历史)。按开始日期倒序,附带天数与「进行中/未开始/已结束」状态。"""
    rows = get_db().execute(
        "SELECT t.*, (SELECT COUNT(*) FROM trip_days d WHERE d.trip_id = t.id) AS day_count "
        "FROM trips t WHERE t.user_id = ? AND t.deleted_at IS NULL "
        "ORDER BY t.start_date DESC, t.id DESC",
        (g.user_id,),
    ).fetchall()
    today = datetime.now().strftime(_DATE_FMT)
    out = []
    for r in rows:
        d = dict(r)
        if today < d["start_date"]:
            d["status"] = "upcoming"
        elif today > d["end_date"]:
            d["status"] = "past"
        else:
            d["status"] = "ongoing"
        out.append(d)
    return jsonify(out)


@travel_bp.route("/api/trips", methods=["POST"])
@login_required
def create_trip():
    """建行程。给了起止日期就自动铺好每一天的空白行,日历直接可用。"""
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    start = (data.get("start_date") or "").strip()
    end = (data.get("end_date") or "").strip()
    if not title:
        return jsonify({"error": "缺少行程名称"}), 400
    if not _valid_date(start) or not _valid_date(end):
        return jsonify({"error": "日期格式应为 YYYY-MM-DD"}), 400
    if _parse_date(end) < _parse_date(start):
        return jsonify({"error": "结束日期不能早于开始日期"}), 400
    span = (_parse_date(end) - _parse_date(start)).days + 1
    if span > 365:
        return jsonify({"error": "单次行程不能超过 365 天"}), 400

    accent = (data.get("accent") or "glacier").strip()
    if accent not in ACCENTS:
        accent = "glacier"

    db = get_db()
    now = _now()
    cur = db.execute(
        "INSERT INTO trips (user_id, title, subtitle, code, start_date, end_date, "
        "accent, cover_note, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (g.user_id, title, (data.get("subtitle") or "").strip() or None,
         (data.get("code") or "").strip() or None, start, end, accent,
         (data.get("cover_note") or "").strip() or None, now, now),
    )
    trip_id = cur.lastrowid

    # 铺每日空行:日历需要每天都有格子,内容后面慢慢填(或 AI 导入)
    d0 = _parse_date(start)
    for i in range(span):
        day = d0 + timedelta(days=i)
        db.execute(
            "INSERT INTO trip_days (trip_id, user_id, day_no, date, detail_json, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (trip_id, g.user_id, i + 1, day.strftime(_DATE_FMT), "{}", now, now),
        )
    db.commit()
    return jsonify({"id": trip_id, "success": True}), 201


@travel_bp.route("/api/trips/<int:trip_id>", methods=["GET"])
@login_required
def get_trip(trip_id: int):
    """行程详情:trip + 全部天 + 打包清单,一次给全(日历要渲染整段)。"""
    trip = _own_trip(trip_id)
    if not trip:
        return jsonify({"error": "行程不存在"}), 404
    db = get_db()
    days = [_day_row_to_dict(r) for r in db.execute(
        "SELECT * FROM trip_days WHERE trip_id = ? ORDER BY day_no ASC", (trip_id,),
    ).fetchall()]
    packs = [dict(r) for r in db.execute(
        "SELECT * FROM trip_pack_items WHERE trip_id = ? ORDER BY sort_order ASC, id ASC",
        (trip_id,),
    ).fetchall()]
    facts = [dict(r) for r in db.execute(
        "SELECT * FROM trip_facts WHERE trip_id = ? ORDER BY sort_order ASC, id ASC",
        (trip_id,),
    ).fetchall()]
    return jsonify({"trip": dict(trip), "days": days, "packing": packs, "facts": facts})


@travel_bp.route("/api/trips/<int:trip_id>", methods=["PATCH"])
@login_required
def update_trip(trip_id: int):
    if not _own_trip(trip_id):
        return jsonify({"error": "行程不存在"}), 404
    data = request.get_json() or {}
    allowed = {"title", "subtitle", "code", "accent", "cover_note"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if "accent" in updates and updates["accent"] not in ACCENTS:
        return jsonify({"error": f"accent 必须是 {'/'.join(sorted(ACCENTS))}"}), 400
    if not updates:
        return jsonify({"error": "无可更新字段"}), 400
    db = get_db()
    sets = ", ".join(f"{k} = ?" for k in updates) + ", updated_at = ?"
    db.execute(f"UPDATE trips SET {sets} WHERE id = ? AND user_id = ?",
               list(updates.values()) + [_now(), trip_id, g.user_id])
    db.commit()
    return jsonify({"success": True})


@travel_bp.route("/api/trips/<int:trip_id>", methods=["DELETE"])
@login_required
def delete_trip(trip_id: int):
    """软删除,与账本一致(可从数据库恢复)。"""
    db = get_db()
    cur = db.execute(
        "UPDATE trips SET deleted_at = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (_now(), trip_id, g.user_id),
    )
    db.commit()
    if cur.rowcount == 0:
        return jsonify({"error": "行程不存在"}), 404
    return jsonify({"success": True})


# ---------- 每日安排 ----------

@travel_bp.route("/api/trips/<int:trip_id>/days/<int:day_no>", methods=["PATCH"])
@login_required
def update_day(trip_id: int, day_no: int):
    """更新某天:路线/交通/含餐/详情结构/手记。detail 整体替换。"""
    if not _own_trip(trip_id):
        return jsonify({"error": "行程不存在"}), 404
    data = request.get_json() or {}
    db = get_db()
    row = db.execute(
        "SELECT id FROM trip_days WHERE trip_id = ? AND day_no = ?", (trip_id, day_no),
    ).fetchone()
    if not row:
        return jsonify({"error": "该天不存在"}), 404

    updates: dict = {}
    for k in ("route", "transport", "meal", "journal"):
        if k in data:
            v = data[k]
            updates[k] = (v.strip() or None) if isinstance(v, str) else v
    if "detail" in data:
        if not isinstance(data["detail"], dict):
            return jsonify({"error": "detail 必须是对象"}), 400
        updates["detail_json"] = json.dumps(data["detail"], ensure_ascii=False)
    if not updates:
        return jsonify({"error": "无可更新字段"}), 400

    sets = ", ".join(f"{k} = ?" for k in updates) + ", updated_at = ?"
    db.execute(f"UPDATE trip_days SET {sets} WHERE id = ?",
               list(updates.values()) + [_now(), row["id"]])
    db.commit()
    return jsonify({"success": True})


# ---------- 打包清单 ----------

@travel_bp.route("/api/trips/<int:trip_id>/packing", methods=["POST"])
@login_required
def add_pack_item(trip_id: int):
    if not _own_trip(trip_id):
        return jsonify({"error": "行程不存在"}), 404
    data = request.get_json() or {}
    label = (data.get("label") or "").strip()
    if not label:
        return jsonify({"error": "缺少条目名称"}), 400
    db = get_db()
    cur = db.execute(
        "INSERT INTO trip_pack_items (trip_id, user_id, grp, label, hint, checked, sort_order) "
        "VALUES (?,?,?,?,?,0,?)",
        (trip_id, g.user_id, (data.get("grp") or "").strip() or None, label,
         (data.get("hint") or "").strip() or None, int(data.get("sort_order") or 0)),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid, "success": True}), 201


@travel_bp.route("/api/trips/<int:trip_id>/packing/<int:item_id>", methods=["PATCH"])
@login_required
def toggle_pack_item(trip_id: int, item_id: int):
    if not _own_trip(trip_id):
        return jsonify({"error": "行程不存在"}), 404
    data = request.get_json() or {}
    db = get_db()
    updates: dict = {}
    if "checked" in data:
        updates["checked"] = 1 if data["checked"] else 0
    for k in ("grp", "label", "hint"):
        if k in data:
            updates[k] = (data[k] or "").strip() or None
    if not updates:
        return jsonify({"error": "无可更新字段"}), 400
    sets = ", ".join(f"{k} = ?" for k in updates)
    cur = db.execute(
        f"UPDATE trip_pack_items SET {sets} WHERE id = ? AND trip_id = ? AND user_id = ?",
        list(updates.values()) + [item_id, trip_id, g.user_id],
    )
    db.commit()
    if cur.rowcount == 0:
        return jsonify({"error": "条目不存在"}), 404
    return jsonify({"success": True})


@travel_bp.route("/api/trips/<int:trip_id>/packing/<int:item_id>", methods=["DELETE"])
@login_required
def delete_pack_item(trip_id: int, item_id: int):
    if not _own_trip(trip_id):
        return jsonify({"error": "行程不存在"}), 404
    db = get_db()
    cur = db.execute(
        "DELETE FROM trip_pack_items WHERE id = ? AND trip_id = ? AND user_id = ?",
        (item_id, trip_id, g.user_id),
    )
    db.commit()
    if cur.rowcount == 0:
        return jsonify({"error": "条目不存在"}), 404
    return jsonify({"success": True})


# ---------- 分享:公开只读链接 ----------
# 安全边界:公开端点不走 login_required,因此**必须**逐字段白名单输出。
# 明确排除:journal(手记)、打包清单、user_id、内部时间戳。
# 只读——没有任何写入入口暴露给匿名访客。

_PUBLIC_TRIP_FIELDS = ("title", "subtitle", "code", "start_date", "end_date",
                       "accent", "cover_note")
_PUBLIC_DAY_FIELDS = ("day_no", "date", "route", "transport", "meal")


@travel_bp.route("/api/trips/<int:trip_id>/share", methods=["GET"])
@login_required
def get_share(trip_id: int):
    if not _own_trip(trip_id):
        return jsonify({"error": "行程不存在"}), 404
    row = get_db().execute(
        "SELECT token, created_at FROM trip_shares "
        "WHERE trip_id = ? AND user_id = ? AND revoked_at IS NULL "
        "ORDER BY id DESC LIMIT 1",
        (trip_id, g.user_id),
    ).fetchone()
    return jsonify({"shared": bool(row), **(dict(row) if row else {})})


@travel_bp.route("/api/trips/<int:trip_id>/share", methods=["POST"])
@login_required
def create_share(trip_id: int):
    """生成(或复用)公开链接。已有未撤销的就直接返回,避免旧链接悄悄失效。"""
    import secrets
    if not _own_trip(trip_id):
        return jsonify({"error": "行程不存在"}), 404
    db = get_db()
    row = db.execute(
        "SELECT token FROM trip_shares WHERE trip_id = ? AND user_id = ? AND revoked_at IS NULL "
        "ORDER BY id DESC LIMIT 1",
        (trip_id, g.user_id),
    ).fetchone()
    if row:
        return jsonify({"token": row["token"], "reused": True})
    token = secrets.token_urlsafe(16)
    db.execute(
        "INSERT INTO trip_shares (trip_id, user_id, token, created_at) VALUES (?,?,?,?)",
        (trip_id, g.user_id, token, _now()),
    )
    db.commit()
    return jsonify({"token": token, "reused": False}), 201


@travel_bp.route("/api/trips/<int:trip_id>/share", methods=["DELETE"])
@login_required
def revoke_share(trip_id: int):
    if not _own_trip(trip_id):
        return jsonify({"error": "行程不存在"}), 404
    db = get_db()
    cur = db.execute(
        "UPDATE trip_shares SET revoked_at = ? "
        "WHERE trip_id = ? AND user_id = ? AND revoked_at IS NULL",
        (_now(), trip_id, g.user_id),
    )
    db.commit()
    return jsonify({"success": True, "revoked": cur.rowcount})


@travel_bp.route("/api/public/trips/<token>", methods=["GET"])
def public_trip(token: str):
    """公开只读行程。**无需登录**——输出严格白名单,不含手记/打包/用户信息。

    token 无效、已撤销、行程已软删,一律 404(不区分,避免探测行程是否存在)。
    """
    if not token or len(token) > 64:
        return jsonify({"error": "链接无效"}), 404
    db = get_db()
    share = db.execute(
        "SELECT trip_id FROM trip_shares WHERE token = ? AND revoked_at IS NULL", (token,),
    ).fetchone()
    if not share:
        return jsonify({"error": "链接无效或已失效"}), 404
    trip = db.execute(
        "SELECT * FROM trips WHERE id = ? AND deleted_at IS NULL", (share["trip_id"],),
    ).fetchone()
    if not trip:
        return jsonify({"error": "链接无效或已失效"}), 404

    trip_out = {k: trip[k] for k in _PUBLIC_TRIP_FIELDS}
    days_out = []
    for r in db.execute(
        "SELECT * FROM trip_days WHERE trip_id = ? ORDER BY day_no ASC", (share["trip_id"],),
    ).fetchall():
        d = {k: r[k] for k in _PUBLIC_DAY_FIELDS}
        try:
            d["detail"] = json.loads(r["detail_json"]) if r["detail_json"] else {}
        except (TypeError, ValueError):
            d["detail"] = {}
        days_out.append(d)          # 注意:journal 不在 _PUBLIC_DAY_FIELDS 里

    # 速查:仅 is_public=1 的条目,且只给 label/body(不给 id/user_id/排序等)
    facts_out = [
        {"label": r["label"], "body": r["body"]}
        for r in db.execute(
            "SELECT label, body FROM trip_facts "
            "WHERE trip_id = ? AND is_public = 1 ORDER BY sort_order ASC, id ASC",
            (share["trip_id"],),
        ).fetchall()
    ]
    # 打包清单始终不公开:是个人准备事项,勾选状态也属于私人进度
    return jsonify({"trip": trip_out, "days": days_out, "facts": facts_out})


# ---------- 速查信息 ----------

@travel_bp.route("/api/trips/<int:trip_id>/facts", methods=["POST"])
@login_required
def add_fact(trip_id: int):
    if not _own_trip(trip_id):
        return jsonify({"error": "行程不存在"}), 404
    data = request.get_json() or {}
    label = (data.get("label") or "").strip()
    if not label:
        return jsonify({"error": "缺少标题"}), 400
    db = get_db()
    now = _now()
    cur = db.execute(
        "INSERT INTO trip_facts (trip_id, user_id, label, body, is_public, sort_order, "
        "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (trip_id, g.user_id, label, (data.get("body") or "").strip() or None,
         1 if data.get("is_public") else 0, int(data.get("sort_order") or 0), now, now),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid, "success": True}), 201


@travel_bp.route("/api/trips/<int:trip_id>/facts/<int:fact_id>", methods=["PATCH"])
@login_required
def update_fact(trip_id: int, fact_id: int):
    if not _own_trip(trip_id):
        return jsonify({"error": "行程不存在"}), 404
    data = request.get_json() or {}
    updates: dict = {}
    for k in ("label", "body"):
        if k in data:
            updates[k] = (data[k] or "").strip() or None
    if "is_public" in data:
        updates["is_public"] = 1 if data["is_public"] else 0
    if "sort_order" in data:
        try:
            updates["sort_order"] = int(data["sort_order"])
        except (TypeError, ValueError):
            return jsonify({"error": "sort_order 必须为整数"}), 400
    if not updates:
        return jsonify({"error": "无可更新字段"}), 400
    if updates.get("label") is None and "label" in updates:
        return jsonify({"error": "标题不能为空"}), 400
    db = get_db()
    sets = ", ".join(f"{k} = ?" for k in updates) + ", updated_at = ?"
    cur = db.execute(
        f"UPDATE trip_facts SET {sets} WHERE id = ? AND trip_id = ? AND user_id = ?",
        list(updates.values()) + [_now(), fact_id, trip_id, g.user_id],
    )
    db.commit()
    if cur.rowcount == 0:
        return jsonify({"error": "条目不存在"}), 404
    return jsonify({"success": True})


@travel_bp.route("/api/trips/<int:trip_id>/facts/<int:fact_id>", methods=["DELETE"])
@login_required
def delete_fact(trip_id: int, fact_id: int):
    if not _own_trip(trip_id):
        return jsonify({"error": "行程不存在"}), 404
    db = get_db()
    cur = db.execute(
        "DELETE FROM trip_facts WHERE id = ? AND trip_id = ? AND user_id = ?",
        (fact_id, trip_id, g.user_id),
    )
    db.commit()
    if cur.rowcount == 0:
        return jsonify({"error": "条目不存在"}), 404
    return jsonify({"success": True})
