#!/usr/bin/env python3
"""把一份静态行程页(手写的 HTML 行程本)导入成账本里的一趟行程。

用法:
    DB_FILE=records.db python3 tools/import_trip.py --html 行程本.html --user admin
    DB_FILE=records.db python3 tools/import_trip.py --html 行程本.html --user admin --trip-id 3 --replace

导入内容:每日安排(时间轴 / 景点 / 贴士 / 拍摄 / 买什么 / 注意 / 住宿 / 地图点)、
打包清单、速查信息。速查一律先设成**私密**:里面有领队和使馆的电话,
是第三方的个人信息,要不要出现在分享链接里由本人逐条决定。
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jsliteral import load_literal  # noqa: E402

_DAY_KEYS = ("sched", "spots", "todo", "cam", "buy", "warn", "stay", "stops")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------- 解析 ----------

def _text(fragment: str) -> str:
    """把速查里的 HTML 片段压成纯文本。

    trip_facts.body 存纯文本而不是 HTML —— 它要渲染到公开分享页上,
    存 HTML 等于给自己留一个 XSS 口子。所以这里把 <br> / 表格行换成换行,
    表头和单元格之间用全角空格分开,其余标签直接丢掉。
    """
    s = re.sub(r"(?i)<br\s*/?>", "\n", fragment)
    s = re.sub(r"(?i)</tr>", "\n", s)
    # span 是「含门票项目」那种并排的小标签，去标签时要补个分隔，不然粘成一长串
    s = re.sub(r"(?i)</(th|td|span)>", "　", s)
    s = re.sub(r"(?i)</?(b|i|em|strong)[^>]*>", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html_mod.unescape(s)
    lines = [re.sub(r"[ \t　]+$", "", ln).strip() for ln in s.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def parse_html(path: Path) -> dict:
    src = path.read_text(encoding="utf-8")

    days_raw = load_literal(src, "const D=")
    pack_raw = load_literal(src, "const PACK=")

    facts = []
    m = re.search(r"const FACTS=`(.*?)`;", src, re.S)
    if m:
        for label, body in re.findall(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", m.group(1), re.S):
            facts.append({"label": _text(label), "body": _text(body)})

    title = "导入的行程"
    sub = None
    h1 = re.search(r"<h1>(.*?)</h1>", src, re.S)
    if h1:
        title = _text(h1.group(1))
    s1 = re.search(r'<div class="sub">(.*?)</div>', src, re.S)
    if s1:
        sub = _text(s1.group(1))

    days = []
    for d in days_raw:
        detail = {k: d[k] for k in _DAY_KEYS if d.get(k)}
        days.append({
            "day_no": int(d["n"]),
            "date": d.get("iso"),
            "route": d.get("r") or None,
            # 静态页把航班 / 车程这类写在标题下的 note 里，对应我们的 transport
            "transport": d.get("note") or None,
            "meal": d.get("meal") or None,
            "detail": detail,
        })
    days.sort(key=lambda x: x["day_no"])

    packing = []
    for grp, items in pack_raw:
        for it in items:
            packing.append({
                "grp": grp,
                "label": it[1] if len(it) > 1 else str(it),
                "hint": (it[2] or None) if len(it) > 2 else None,
            })

    return {"title": title, "subtitle": sub, "days": days, "packing": packing, "facts": facts}


# ---------- 写库 ----------

def _user_id(conn, username: str) -> int:
    row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if not row:
        sys.exit(f"没有这个用户:{username}")
    return row[0]


def _ensure_trip(conn, uid: int, data: dict, args) -> int:
    if args.trip_id:
        row = conn.execute(
            "SELECT id FROM trips WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (args.trip_id, uid),
        ).fetchone()
        if not row:
            sys.exit(f"行程 {args.trip_id} 不存在或不属于该用户")
        return row[0]

    start = data["days"][0]["date"]
    end = data["days"][-1]["date"]
    now = _now()
    cur = conn.execute(
        "INSERT INTO trips (user_id, title, subtitle, code, start_date, end_date, accent, "
        "cover_note, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (uid, args.title or data["title"], args.subtitle or data["subtitle"], args.code,
         start, end, args.accent, args.cover_note, now, now),
    )
    return cur.lastrowid


def import_trip(db_path: str, data: dict, args) -> dict:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    uid = _user_id(conn, args.user)
    trip_id = _ensure_trip(conn, uid, data, args)
    now = _now()
    stat = {"trip_id": trip_id, "days": 0, "packing": 0, "facts": 0}

    for d in data["days"]:
        detail = json.dumps(d["detail"], ensure_ascii=False)
        cur = conn.execute(
            "UPDATE trip_days SET route = ?, transport = ?, meal = ?, detail_json = ?, "
            "updated_at = ? WHERE trip_id = ? AND day_no = ?",
            (d["route"], d["transport"], d["meal"], detail, now, trip_id, d["day_no"]),
        )
        if cur.rowcount == 0:
            # 建行程时会按起止日期铺好每一天；导入到已有行程时可能缺，补上
            conn.execute(
                "INSERT INTO trip_days (trip_id, user_id, day_no, date, route, transport, meal, "
                "detail_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (trip_id, uid, d["day_no"], d["date"], d["route"], d["transport"], d["meal"],
                 detail, now, now),
            )
        stat["days"] += 1

    if args.replace:
        conn.execute("DELETE FROM trip_pack_items WHERE trip_id = ?", (trip_id,))
        conn.execute("DELETE FROM trip_facts WHERE trip_id = ?", (trip_id,))

    have_pack = conn.execute(
        "SELECT COUNT(*) FROM trip_pack_items WHERE trip_id = ?", (trip_id,)).fetchone()[0]
    if not have_pack:
        for i, p in enumerate(data["packing"]):
            conn.execute(
                "INSERT INTO trip_pack_items (trip_id, user_id, grp, label, hint, checked, "
                "sort_order) VALUES (?,?,?,?,?,0,?)",
                (trip_id, uid, p["grp"], p["label"], p["hint"], i),
            )
            stat["packing"] += 1

    have_facts = conn.execute(
        "SELECT COUNT(*) FROM trip_facts WHERE trip_id = ?", (trip_id,)).fetchone()[0]
    if not have_facts:
        for i, f in enumerate(data["facts"]):
            # is_public 一律 0：里面有领队和使馆电话，公开与否本人逐条决定
            conn.execute(
                "INSERT INTO trip_facts (trip_id, user_id, label, body, is_public, sort_order, "
                "created_at, updated_at) VALUES (?,?,?,?,0,?,?,?)",
                (trip_id, uid, f["label"], f["body"], i, now, now),
            )
            stat["facts"] += 1

    conn.commit()
    conn.close()
    return stat


def main() -> None:
    ap = argparse.ArgumentParser(description="把静态行程页导入成账本里的一趟行程")
    ap.add_argument("--html", required=True, type=Path)
    ap.add_argument("--user", required=True, help="导入到哪个用户名下")
    ap.add_argument("--db", default=os.getenv("DB_FILE", "records.db"))
    ap.add_argument("--trip-id", type=int, help="导入到已有行程；不给则新建")
    ap.add_argument("--title")
    ap.add_argument("--subtitle")
    ap.add_argument("--code", help="团号，可空")
    ap.add_argument("--cover-note")
    ap.add_argument("--accent", default="glacier")
    ap.add_argument("--replace", action="store_true",
                    help="覆盖已有的打包清单与速查（默认只在为空时才写，避免冲掉勾选进度）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = parse_html(args.html)
    print(f"解析到 {len(data['days'])} 天、{len(data['packing'])} 条打包、{len(data['facts'])} 条速查")
    if args.dry_run:
        print(json.dumps(data["days"][0], ensure_ascii=False, indent=2)[:1200])
        return
    stat = import_trip(args.db, data, args)
    print(f"完成:行程 #{stat['trip_id']}，写入 {stat['days']} 天 / "
          f"{stat['packing']} 条打包 / {stat['facts']} 条速查")
    if stat["facts"]:
        print("速查全部先设为私密（含领队、使馆电话）。要出现在分享页，请在速查页逐条点开。")


if __name__ == "__main__":
    main()
