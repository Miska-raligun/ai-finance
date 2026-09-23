"""当天详情(detail_json)的结构处理。

这里只放不依赖 Flask / LLM 的纯函数,数据迁移和运行时都要用。

历史包袱:同一批地点原来分两处存——「景点」(spots,只有名字和停留时长)
和「地图停留点」(stops,有坐标、介绍、照片)。于是改了景点的名字,地图上
那个点还叫老名字,两边对不上。现在合成一份:stops 就是这一天的地点,
没有坐标的也留着,只是不画在地图上。
"""
from __future__ import annotations

import re
import unicodedata

# 名字里不影响"是不是同一个地方"的字符。括号本身去掉,但**不去掉括号里的内容**
# ——「大教堂(旧城)」和「大教堂(新区)」的区别恰恰在里面。
_NOISE = re.compile(r"[\s·・\-—_.,、。'\"“”‘’()()\[\]【】「」《》!!??::;;/\\|]+")

# 长度比的下限,分两档——差别在于多出来的字加在哪里:
#   * 加在两头(「岩石教堂」→「赫尔辛基岩石教堂」):短名是长名的**子串**,
#     这是最常见的"加个城市名"写法,判起来很稳,门槛可以松
#   * 插在中间(「颂歌图书馆」→「颂歌中央图书馆」):只是**子序列**。危险的
#     误判都在这一档——「赫尔辛基大教堂」也是「赫尔辛基乌斯别斯基大教堂」的
#     子序列,但那是两座教堂。所以门槛收紧,让 7/12≈0.58 掉下去,
#     而 5/7≈0.71 留下来
_RATIO_SUBSTR = 0.4
_RATIO_SUBSEQ = 0.62
# 都有坐标却隔着十几公里,名字再像也是两个地方
_MAX_KM = 2.0


def _s(v, limit: int) -> str:
    return str(v).strip()[:limit] if isinstance(v, (str, int, float)) else ""


def _norm(name: str) -> str:
    """归一化:全角转半角、去掉标点空格、拉丁字母统一小写。"""
    s = unicodedata.normalize("NFKC", name or "").strip()
    return _NOISE.sub("", s).casefold()


def _subseq(short: str, long: str) -> bool:
    """short 的字按顺序都能在 long 里找到(不要求连着)。

    中文地名的差别常是往中间插字:「颂歌图书馆」→「颂歌中央图书馆」。
    这种"包含子串"判不出来,得看子序列。
    """
    it = iter(long)
    return all(ch in it for ch in short)


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None          # NaN 不算


def _far_apart(a: dict, b: dict) -> bool:
    la, lna = _num(a.get("lat")), _num(a.get("lng"))
    lb, lnb = _num(b.get("lat")), _num(b.get("lng"))
    if None in (la, lna, lb, lnb):
        return False                      # 有一边没坐标,这条判据用不上
    # 够用的粗算:1 度纬度约 111km,经度按纬度收缩。几公里的量级不需要大圆距离
    import math
    dy = (la - lb) * 111.0
    dx = (lna - lnb) * 111.0 * max(0.1, math.cos(math.radians((la + lb) / 2)))
    return math.hypot(dx, dy) > _MAX_KM


def same_place(a: dict, b: dict) -> bool:
    """两条 stop 是不是同一个地方。

    只认两种情况:归一化之后完全一样,或者短的是长的子序列且长度接近。
    宁可漏判也不要误判——漏判留下一个重复的地点,用户看得见也删得掉;
    误判是把两个地方悄悄并成一个,连同其中一个的照片和介绍一起没了。
    """
    na, nb = _norm(a.get("t") or ""), _norm(b.get("t") or "")
    if not na or not nb:
        return False
    if na == nb:
        return not _far_apart(a, b)
    short, long = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(short) < 2:
        return False
    ratio = len(short) / len(long)
    if short in long:
        ok = ratio >= _RATIO_SUBSTR
    else:
        ok = ratio >= _RATIO_SUBSEQ and _subseq(short, long)
    return ok and not _far_apart(a, b)


def _absorb(keep: dict, drop: dict) -> None:
    """把 drop 上有、keep 上没有的字段搬过去,然后用更具体的那个名字。

    名字取长的:「颂歌中央图书馆」比「颂歌图书馆」更好找,也更接近正式名。
    这两个名字都是 AI 写的,不是用户敲的,所以改名不会盖掉谁的输入。
    """
    for k, v in drop.items():
        if k == "t":
            continue
        if k not in keep or keep[k] in (None, "", [], 0):
            keep[k] = v
    if len(drop.get("t") or "") > len(keep.get("t") or ""):
        keep["t"] = drop["t"]


def dedupe_stops(stops: list) -> list:
    """把同一个地方的重复条目并掉。

    模型在同一次回复里给两份地点清单时,名字常会飘一两个字
    (「颂歌图书馆」/「颂歌中央图书馆」),于是一个带坐标、一个不带,
    地图上那个正常,列表里那个永远显示"未定位"。
    """
    out: list = []
    for st in stops or []:
        if not isinstance(st, dict) or not _s(st.get("t"), 60):
            continue
        hit = next((o for o in out if same_place(o, st)), None)
        if hit is None:
            out.append(st)
        else:
            _absorb(hit, st)
    return out


def merge_spots_into_stops(detail: dict) -> dict:
    """把 detail 里的 spots 并进 stops,并去掉 spots 这个键。

    同一个地方的合并:停留时长挂到已有的点上,坐标 / 介绍 / 照片一个不动。
    没对上的按原顺序接在后面——它们没有坐标,地图上不画,但在地点列表里
    照样看得见,也照样能挂照片,之后补上坐标就会出现在地图上。

    返回的是同一个 dict(就地改)。
    """
    if not isinstance(detail, dict):
        return detail
    raw_spots = detail.pop("spots", None)
    stops = detail.get("stops")
    if not isinstance(stops, list):
        stops = []

    for row in (raw_spots if isinstance(raw_spots, list) else []):
        if isinstance(row, str):
            row = [row]
        elif isinstance(row, dict):
            row = [row.get("name") or row.get("t"), row.get("dur")]
        if not isinstance(row, list) or not row:
            continue
        name = _s(row[0], 60)
        if not name:
            continue
        item = {"t": name}
        dur = _s(row[1], 40) if len(row) > 1 else ""
        if dur:
            item["dur"] = dur
        stops.append(item)

    stops = dedupe_stops(stops)
    if stops:
        detail["stops"] = stops
    elif "stops" in detail:
        del detail["stops"]
    return detail
