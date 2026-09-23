"""0027 把「景点」(spots)并进「地图停留点」(stops)。

同一批地点原来分两处存:spots 只有名字和停留时长,stops 有坐标、介绍、照片。
于是改了景点的名字,地图上那个点还是老名字,两边对不上;想给一个没坐标的
地点挂照片也没处挂。

合并规则见 services/trip_detail.merge_spots_into_stops:同名的把时长补到
已有的点上,坐标/介绍/照片一个不动;没对上的接在后面(没坐标,地图上不画,
但列表里看得见)。

只改 detail_json 里的这两个键,别的原样写回。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.trip_detail import merge_spots_into_stops  # noqa: E402


def migrate(conn) -> None:
    rows = conn.execute(
        "SELECT id, detail_json FROM trip_days WHERE detail_json LIKE '%\"spots\"%'"
    ).fetchall()
    for row in rows:
        rid, raw = row[0], row[1]
        try:
            detail = json.loads(raw or "{}")
        except (TypeError, ValueError):
            continue                      # 本来就不是合法 JSON,别在迁移里放大问题
        if not isinstance(detail, dict) or "spots" not in detail:
            continue
        merge_spots_into_stops(detail)
        conn.execute("UPDATE trip_days SET detail_json = ? WHERE id = ?",
                     (json.dumps(detail, ensure_ascii=False), rid))
