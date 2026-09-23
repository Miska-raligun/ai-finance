"""把一趟行程导出成**一个**自带全部内容的 HTML 文件。

为什么做这个:在路上常常没网——境外漫游没开、飞机上、山里。行程本身是
离线也该能看的东西。所以导出的文件里不能有任何外部引用:样式内联、
照片转成 data URI、地图换成不依赖瓦片的路线示意图。

PDF 不在服务端生成(那要额外拖一个渲染器进来),文件里带一个打印按钮,
浏览器自己就能存成 PDF——和月报导出一个路子。
"""
from __future__ import annotations

import base64
import html
import json
import math
import os
from datetime import datetime

from db import get_db

# 照片按 base64 内嵌会涨三分之一,给个总量上限,超了就停下并在文件里说明
_PHOTO_BUDGET = 24 * 1024 * 1024
_PHOTOS_PER_DAY = 6

_WEEK = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

ACCENTS = {
    "glacier": ("#2B6A80", "#D9E6EB", "#17414f"),
    "aurora": ("#3C8C6E", "#D8EBE2", "#215240"),
    "ember": ("#9A5A2C", "#F3E6D8", "#5e3418"),
    "sakura": ("#B4576F", "#F6E1E6", "#6d2f3f"),
    "desert": ("#A8843C", "#F2E9D4", "#5f4a1c"),
    "violet": ("#6A5A9A", "#E5E1F1", "#3d3363"),
}


def _e(v) -> str:
    return html.escape(str(v)) if v is not None else ""


def _pretty(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        d = datetime.strptime(iso, "%Y-%m-%d").date()
    except ValueError:
        return iso
    return f"{d.month} 月 {d.day} 日 · {_WEEK[d.weekday()]}"


# ---------- 路线示意图 ----------

def _route_svg(points: list[dict], color: str, weak: str) -> str:
    """不依赖瓦片的路线示意图:等距圆柱投影 + 编号圆点,名字放到下面的列表里。

    没有底图,所以它是「示意」不是「地图」——但相对位置和先后顺序是真的,
    离线时用来对着看"今天大概往哪个方向走"足够了。编号而不是直接标名字,
    是为了不用做标签避让:点挤在一起时名字必然重叠,编号不会。
    """
    if len(points) < 2:
        return ""
    lats = sorted(p["lat"] for p in points)
    lngs = sorted(p["lng"] for p in points)

    def at(arr, t):
        return arr[max(0, min(len(arr) - 1, round((len(arr) - 1) * t)))]

    # 一条长途航段会把视野撑到半个地球,取中间 90% 的点定范围
    if len(points) >= 8:
        box = (at(lats, .05), at(lats, .95), at(lngs, .05), at(lngs, .95))
        full = (lats[0], lats[-1], lngs[0], lngs[-1])
        area = lambda b: max(b[1] - b[0], 1e-6) * max(b[3] - b[2], 1e-6)  # noqa: E731
        if area(box) >= area(full) * 0.5:
            box = full
    else:
        box = (lats[0], lats[-1], lngs[0], lngs[-1])
    min_lat, max_lat, min_lng, max_lng = box

    W, H, pad = 720, 300, 26
    k = math.cos(((min_lat + max_lat) / 2) * math.pi / 180) or 1  # 高纬度横向要压缩
    span_x = max((max_lng - min_lng) * k, 1e-6)
    span_y = max(max_lat - min_lat, 1e-6)
    s = min((W - pad * 2) / span_x, (H - pad * 2) / span_y)
    off_x = (W - span_x * s) / 2
    off_y = (H - span_y * s) / 2

    def xy(p):
        return (off_x + (p["lng"] - min_lng) * k * s,
                off_y + (max_lat - p["lat"]) * s)

    coords = [xy(p) for p in points]
    path = "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in coords)
    dots = []
    for (x, y), p in zip(coords, points):
        if not (-20 < x < W + 20 and -20 < y < H + 20):
            continue
        dots.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="#fff"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8.5" fill="{color}"/>'
            f'<text x="{x:.1f}" y="{y + 2.8:.1f}" text-anchor="middle" '
            f'font-size="8.5" font-weight="700" fill="#fff">{_e(p["no"])}</text>'
        )
    legend = "".join(
        f'<li><b>{_e(p["no"])}</b>{_e(p["t"])}</li>' for p in points
    )
    return (
        '<section class="card"><h2>路线示意</h2>'
        '<p class="dim">一天一个点,按天连线。没有底图,只表示相对位置和先后——'
        '离线时用来对方向,具体导航还得联网。</p>'
        f'<svg viewBox="0 0 {W} {H}" class="routemap" role="img" aria-label="路线示意图">'
        f'<rect width="{W}" height="{H}" rx="10" fill="{weak}"/>'
        f'<path d="{path}" fill="none" stroke="{color}" stroke-width="1.6" '
        'stroke-dasharray="5 4" opacity=".75"/>'
        + "".join(dots) + "</svg>"
        f'<ol class="routelist">{legend}</ol></section>'
    )


# ---------- 取数 ----------

def _photo_data_uri(path: str, mime: str) -> str | None:
    from services.trip_photos import absolute_path
    full = absolute_path(path)
    if not os.path.isfile(full):
        return None
    with open(full, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def build_html(user_id: int, trip: dict, *, scope: str = "full",
               with_photos: bool = True) -> str:
    """scope='full' 连手记和打包清单一起导出(自己留着看);
    scope='share' 与分享链接口径一致,可以安心发给同行的人。"""
    db = get_db()
    trip_id = trip["id"]
    share_only = scope == "share"

    days = []
    for r in db.execute(
        "SELECT * FROM trip_days WHERE trip_id = ? ORDER BY day_no ASC", (trip_id,),
    ).fetchall():
        d = dict(r)
        try:
            d["detail"] = json.loads(d.get("detail_json") or "{}")
        except (TypeError, ValueError):
            d["detail"] = {}
        days.append(d)

    facts = [dict(r) for r in db.execute(
        "SELECT label, body, is_public FROM trip_facts WHERE trip_id = ? "
        "ORDER BY sort_order ASC, id ASC", (trip_id,),
    ).fetchall()]
    if share_only:
        facts = [f for f in facts if f["is_public"]]

    packing = [] if share_only else [dict(r) for r in db.execute(
        "SELECT grp, label, hint, checked FROM trip_pack_items WHERE trip_id = ? "
        "ORDER BY sort_order ASC, id ASC", (trip_id,),
    ).fetchall()]

    photo_rows = {}
    if with_photos:
        for r in db.execute(
            "SELECT sha256, mime, path FROM trip_photos WHERE trip_id = ?", (trip_id,),
        ).fetchall():
            photo_rows[r["sha256"]] = dict(r)

    color, weak, ink = ACCENTS.get(trip.get("accent") or "", ACCENTS["glacier"])

    # 路线示意图:**一天一个点**。
    # 按停留点逐个画的话,十四天六十多个点会在几个城市上挤成一坨,编号互相盖住,
    # 反而看不出走向。一天一个点(取当天停留点的中心)正好是"每天往哪儿走"。
    pts = []
    for d in days:
        day_pts = []
        for st in (d["detail"].get("stops") or []):
            try:
                day_pts.append((float(st["lat"]), float(st["lng"])))
            except (KeyError, TypeError, ValueError):
                continue
        if not day_pts:
            continue
        pts.append({
            "no": f'D{d["day_no"]}',
            "t": d.get("route") or (d.get("date") or ""),
            "lat": sum(p[0] for p in day_pts) / len(day_pts),
            "lng": sum(p[1] for p in day_pts) / len(day_pts),
        })

    budget = [_PHOTO_BUDGET]
    truncated = [False]

    def photo_tags(stops) -> str:
        if not with_photos:
            return ""
        tags = []
        for st in stops:
            shas = st.get("photos") or ([st["photo"]] if st.get("photo") else [])
            for sha in shas[:_PHOTOS_PER_DAY]:
                row = photo_rows.get(sha)
                if not row:
                    continue
                if budget[0] <= 0:
                    truncated[0] = True
                    break
                uri = _photo_data_uri(row["path"], row["mime"])
                if not uri:
                    continue
                budget[0] -= len(uri)
                tags.append(f'<img src="{uri}" alt="">')
        return f'<div class="shots">{"".join(tags)}</div>' if tags else ""

    parts: list[str] = []
    for d in days:
        x = d["detail"]
        body = []
        chips = []
        if d.get("transport"):
            chips.append(f'<span class="chip">{_e(d["transport"])}</span>')
        if d.get("meal"):
            chips.append(f'<span class="chip ghost">含餐 {_e(d["meal"])}</span>')
        if chips:
            body.append(f'<div class="chips">{"".join(chips)}</div>')

        sched = x.get("sched") or []
        if sched:
            rows = "".join(
                f'<li><time>{_e(s[0] if len(s) > 0 else "")}</time>'
                f'<span><b>{_e(s[1] if len(s) > 1 else "")}</b>'
                + (f'<em>{_e(s[2])}</em>' if len(s) > 2 and s[2] else "")
                + "</span></li>"
                for s in sched if isinstance(s, list) and len(s) > 1
            )
            body.append(f'<ol class="sched">{rows}</ol>')

        # 地点就是 stops 那一份(没坐标的也在里面,只是地图上不画)
        places = [st for st in (x.get("stops") or []) if isinstance(st, dict) and st.get("t")]
        if places:
            lis = "".join(
                f'<li>{_e(st["t"])}'
                + (f'<span class="dim"> · {_e(st["dur"])}</span>' if st.get("dur") else "")
                + "</li>" for st in places)
            body.append(f'<div class="sub"><h4>地点</h4><ul>{lis}</ul></div>')

        for key, label in (("todo", "贴士"), ("cam", "拍摄建议"),
                           ("buy", "买什么"), ("warn", "注意")):
            items = x.get(key) or []
            if not items:
                continue
            lis = "".join(f"<li>{_e(i)}</li>" for i in items)
            body.append(f'<div class="sub"><h4>{label}</h4><ul>{lis}</ul></div>')

        stay = x.get("stay") or {}
        if stay.get("h") or stay.get("a"):
            body.append(
                '<div class="stay"><b>🏨 ' + _e(stay.get("h")) + "</b>"
                + (f'<span>{_e(stay.get("a"))}</span>' if stay.get("a") else "")
                + "</div>")

        body.append(photo_tags(x.get("stops") or []))

        if not share_only and (d.get("journal") or "").strip():
            body.append('<div class="sub journal"><h4>我的手记</h4><p>'
                        + _e(d["journal"]) + "</p></div>")

        if not any(b for b in body if b):
            body = ['<p class="dim">这一天还没有填安排。</p>']

        parts.append(
            f'<section class="card day"><div class="dayhead">'
            f'<span class="dayno">Day {d["day_no"]}</span>'
            f'<h3>{_e(d.get("route") or "自由活动")}</h3>'
            f'<span class="date">{_pretty(d.get("date"))}</span></div>'
            + "".join(body) + "</section>")

    facts_html = ""
    if facts:
        items = "".join(
            f'<div class="fact"><h4>{_e(f["label"])}'
            + ("" if share_only or f["is_public"] else '<span class="tag">私密</span>')
            + f'</h4><p>{_e(f["body"])}</p></div>' for f in facts)
        facts_html = f'<section class="card"><h2>速查</h2>{items}</section>'

    pack_html = ""
    if packing:
        groups: dict[str, list] = {}
        for it in packing:
            groups.setdefault(it["grp"] or "其它", []).append(it)
        blocks = "".join(
            f'<div class="pkg"><h4>{_e(g)}</h4><ul>'
            + "".join(
                f'<li>{"☑" if it["checked"] else "☐"} {_e(it["label"])}'
                + (f'<span class="dim"> · {_e(it["hint"])}</span>' if it["hint"] else "")
                + "</li>" for it in its)
            + "</ul></div>" for g, its in groups.items())
        pack_html = f'<section class="card"><h2>打包清单</h2><div class="pkgs">{blocks}</div></section>'

    note = (f'<p class="cover">{_e(trip.get("cover_note"))}</p>'
            if trip.get("cover_note") else "")
    warn = ('<p class="dim">照片太多,文件里只放下了一部分。</p>' if truncated[0] else "")
    kind = "完整版（含手记与打包清单）" if not share_only else "分享版（与分享链接口径一致）"

    return _SHELL.format(
        title=_e(trip.get("title") or "行程"),
        color=color, weak=weak, ink=ink,
        code=(f'<div class="code">{_e(trip["code"])}</div>' if trip.get("code") else ""),
        head_title=_e(trip.get("title") or "行程"),
        sub=(f'<div class="sub-t">{_e(trip["subtitle"])}</div>' if trip.get("subtitle") else ""),
        note=note,
        range=f'{_e(trip.get("start_date"))} — {_e(trip.get("end_date"))} · 共 {len(days)} 天',
        routemap=_route_svg(pts, color, weak),
        facts=facts_html,
        days="".join(parts),
        packing=pack_html,
        warn=warn,
        kind=_e(kind),
        stamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


_SHELL = """<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ --a: {color}; --w: {weak}; --i: {ink}; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: #f5f3ea; color: #33302a;
    font: 15px/1.7 -apple-system, BlinkMacSystemFont, "PingFang SC",
          "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  }}
  .wrap {{ max-width: 860px; margin: 0 auto; padding: 0 16px 40px; }}
  header {{ background: linear-gradient(140deg, var(--w), #fff 130%);
            border-bottom: 3px solid var(--a); padding: 30px 0 24px; margin-bottom: 18px; }}
  header .wrap {{ padding-bottom: 0; }}
  .code {{ display: inline-block; font-size: 11px; letter-spacing: .1em; color: var(--i);
           border: 1px solid var(--a); border-radius: 999px; padding: 2px 10px; }}
  h1 {{ margin: 10px 0 0; font-size: 28px; color: var(--i); }}
  .sub-t {{ margin-top: 4px; color: var(--i); opacity: .8; }}
  .cover {{ margin: 12px 0 0; padding-left: 10px; border-left: 3px solid var(--a);
            color: var(--i); opacity: .85; font-size: 14px; }}
  .range {{ margin-top: 12px; font-size: 13px; color: var(--i); opacity: .72; }}
  .card {{ background: #fff; border: 1px solid #e3ddd0; border-radius: 14px;
           padding: 16px 18px; margin-bottom: 14px; }}
  h2 {{ margin: 0 0 10px; font-size: 15px; }}
  .dim {{ color: #8a8577; font-size: 13px; }}
  .routemap {{ width: 100%; height: auto; display: block; }}
  .routelist {{ list-style: none; margin: 10px 0 0; padding: 0; display: flex;
                flex-wrap: wrap; gap: 6px 14px; font-size: 12.5px; }}
  .routelist li {{ display: flex; align-items: baseline; gap: 5px; }}
  .routelist b {{ display: inline-grid; place-items: center; min-width: 26px; height: 17px;
                  padding: 0 5px; border-radius: 999px; background: var(--a); color: #fff;
                  font-size: 10px; }}
  .routelist span {{ color: #8a8577; font-size: 11px; }}
  .dayhead {{ display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }}
  .dayno {{ font-size: 11px; font-weight: 800; color: #fff; background: var(--a);
            padding: 2px 9px; border-radius: 999px; }}
  .dayhead h3 {{ margin: 0; font-size: 17px; flex: 1; }}
  .date {{ font-size: 12px; color: #8a8577; }}
  .chips {{ margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap; }}
  .chip {{ font-size: 11px; padding: 2px 9px; border-radius: 999px;
           background: var(--w); color: var(--i); }}
  .chip.ghost {{ background: none; border: 1px solid #e3ddd0; color: #8a8577; }}
  .sched {{ list-style: none; margin: 12px 0 0; padding: 0; }}
  .sched li {{ display: flex; gap: 12px; padding: 3px 0; }}
  .sched time {{ width: 46px; flex-shrink: 0; text-align: right; font-size: 12px;
                 color: #8a8577; }}
  .sched em {{ display: block; font-style: normal; font-size: 12px; color: #8a8577; }}
  .sub {{ margin-top: 12px; }}
  .sub h4 {{ margin: 0 0 3px; font-size: 11px; letter-spacing: .08em; color: var(--a); }}
  .sub ul {{ margin: 0; padding-left: 18px; font-size: 13.5px; }}
  .stay {{ margin-top: 12px; padding-top: 10px; border-top: 1px dashed #e3ddd0;
           font-size: 13.5px; display: flex; flex-direction: column; }}
  .stay span {{ color: #8a8577; font-size: 12.5px; }}
  .journal p {{ margin: 0; white-space: pre-wrap; font-size: 13.5px; }}
  .shots {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-top: 12px; }}
  .shots img {{ width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 8px; }}
  .fact {{ padding: 8px 0; border-bottom: 1px solid #f0ece2; }}
  .fact:last-child {{ border-bottom: 0; }}
  .fact h4 {{ margin: 0 0 3px; font-size: 12px; letter-spacing: .06em; color: #8a8577; }}
  .fact p {{ margin: 0; white-space: pre-wrap; font-size: 13.5px; }}
  .tag {{ margin-left: 6px; font-size: 10px; color: #b4576f; }}
  .pkgs {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; }}
  .pkg h4 {{ margin: 0 0 3px; font-size: 12px; color: var(--a); }}
  .pkg ul {{ list-style: none; margin: 0; padding: 0; font-size: 13px; }}
  footer {{ text-align: center; font-size: 11px; color: #8a8577; padding: 10px 0 30px; }}
  .bar {{ position: sticky; top: 0; z-index: 9; background: rgba(245,243,234,.94);
          border-bottom: 1px solid #e3ddd0; padding: 8px 16px; text-align: right; }}
  .bar button {{ font: inherit; font-size: 13px; padding: 5px 14px; cursor: pointer;
                 border: 1px solid var(--a); background: #fff; color: var(--a);
                 border-radius: 999px; }}
  @media print {{
    body {{ background: #fff; }}
    .bar {{ display: none; }}
    .card {{ break-inside: avoid; border-color: #ddd; }}
    header {{ background: none; }}
  }}
</style></head><body>
<div class="bar"><button onclick="window.print()">🖨️ 打印 / 另存为 PDF</button></div>
<header><div class="wrap">
  {code}<h1>{head_title}</h1>{sub}{note}
  <div class="range">{range}</div>
</div></header>
<div class="wrap">
  {routemap}
  {facts}
  {days}
  {packing}
  {warn}
</div>
<footer>{kind} · 导出于 {stamp} · 这份文件不依赖网络</footer>
</body></html>
"""
