"""当天详情(detail_json)的结构处理。

这里只放不依赖 Flask / LLM 的纯函数,数据迁移和运行时都要用。

历史包袱:同一批地点原来分两处存——「景点」(spots,只有名字和停留时长)
和「地图停留点」(stops,有坐标、介绍、照片)。于是改了景点的名字,地图上
那个点还叫老名字,两边对不上。现在合成一份:stops 就是这一天的地点,
没有坐标的也留着,只是不画在地图上。
"""
from __future__ import annotations


def _s(v, limit: int) -> str:
    return str(v).strip()[:limit] if isinstance(v, (str, int, float)) else ""


def merge_spots_into_stops(detail: dict) -> dict:
    """把 detail 里的 spots 并进 stops,并去掉 spots 这个键。

    同名的合并:停留时长挂到已有的点上,坐标 / 介绍 / 照片一个不动。
    没对上的按原顺序接在后面——它们没有坐标,地图上不画,但在地点列表里
    照样看得见,也照样能挂照片,之后补上坐标就会出现在地图上。

    返回的是同一个 dict(就地改),没有 spots 时原样返回。
    """
    if not isinstance(detail, dict):
        return detail
    raw_spots = detail.pop("spots", None)
    if not isinstance(raw_spots, list) or not raw_spots:
        return detail

    stops = detail.get("stops")
    if not isinstance(stops, list):
        stops = []
    by_name: dict[str, dict] = {}
    for st in stops:
        if isinstance(st, dict):
            by_name.setdefault(_s(st.get("t"), 60), st)

    for row in raw_spots:
        if isinstance(row, str):
            row = [row]
        elif isinstance(row, dict):
            row = [row.get("name") or row.get("t"), row.get("dur")]
        if not isinstance(row, list) or not row:
            continue
        name = _s(row[0], 60)
        if not name:
            continue
        dur = _s(row[1], 40) if len(row) > 1 else ""
        hit = by_name.get(name)
        if hit is not None:
            # 已经在地图上了:只把时长补上,别的字段一个不碰
            if dur and not _s(hit.get("dur"), 40):
                hit["dur"] = dur
            continue
        new = {"t": name}
        if dur:
            new["dur"] = dur
        stops.append(new)
        by_name[name] = new

    if stops:
        detail["stops"] = stops
    return detail
