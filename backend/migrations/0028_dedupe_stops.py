"""0028 把同一个地方的重复地点并掉。

0027 把「景点」并进「地图停留点」时用的是**名字完全相等**,于是模型在同一次
回复里写飘了一两个字的,就成了两条:「颂歌图书馆」有坐标、在地图上,
「颂歌中央图书馆」没坐标、在列表里永远显示"未定位"。

合并规则见 services/trip_detail.same_place。这一趟对所有天跑一遍,
不只是 0027 动过的那些——同样的重复也可能是 AI 生成时就带进来的。

只在真的变了的时候写回,库里没这个毛病的行一个都不动。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.trip_detail import dedupe_stops  # noqa: E402


def migrate(conn) -> None:
    rows = conn.execute(
        "SELECT id, detail_json FROM trip_days WHERE detail_json LIKE '%\"stops\"%'"
    ).fetchall()
    for row in rows:
        rid, raw = row[0], row[1]
        try:
            detail = json.loads(raw or "{}")
        except (TypeError, ValueError):
            continue
        if not isinstance(detail, dict) or not isinstance(detail.get("stops"), list):
            continue
        merged = dedupe_stops(detail["stops"])
        if len(merged) == len(detail["stops"]):
            continue                      # 没有重复,不写
        detail["stops"] = merged
        conn.execute("UPDATE trip_days SET detail_json = ? WHERE id = ?",
                     (json.dumps(detail, ensure_ascii=False), rid))
