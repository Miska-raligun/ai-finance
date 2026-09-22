"""行程 AI 生成:骨架 → 按天细化 → 单块重写。

为什么分三层:一次调用做不出一份 14 天的完整行程——输出太长,模型会漏天、
会把 JSON 写坏,而且一旦失败整趟白跑。拆开之后每次调用的输出都小而可校验,
失败只需重跑那一段。

所有模型输出都**先清洗再落库**:行程详情会渲染到公开分享页上,不能把模型
吐出来的任意结构原样存进 detail_json。清洗做三件事——限长、限条数、
丢掉不合法的坐标。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta

from prompts.travel import (
    BLOCK_KINDS, DAY_SYSTEM, FACTS_EXTRACT_SYSTEM, OUTLINE_SYSTEM,
    SPOT_DESCS_SYSTEM, build_block_prompt, build_day_prompt,
    build_facts_extract_prompt, build_outline_from_idea,
    build_outline_from_notice, build_spot_descs_prompt,
)

from services.trip_detail import merge_spots_into_stops

logger = logging.getLogger(__name__)

_DATE_FMT = "%Y-%m-%d"
MAX_DAYS = 30                  # AI 细化的上限,兜住 token 成本
ACCENTS = ("glacier", "aurora", "ember", "sakura", "desert", "violet")


class AIError(Exception):
    """模型没给出可用结果。message 直接给用户看。"""


# ---------- 调用与解析 ----------

def _json_call(system: str, user: str, *, endpoint: str, timeout: int,
               temperature: float = 0.3, llm: dict | None = None):
    from services.llm import _call_llm

    res = _call_llm(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        llm=llm, temperature=temperature, timeout=timeout, endpoint=endpoint,
    )
    if not res:
        raise AIError("模型没有返回内容")
    if "error" in res:
        msg = res["error"].get("message") if isinstance(res["error"], dict) else str(res["error"])
        raise AIError(msg or "模型调用失败")
    try:
        content = res["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise AIError("模型返回结构异常")

    parsed = _loads_loose(content)
    if parsed is None:
        logger.warning("travel_ai %s: JSON 解析失败,前 200 字=%s", endpoint, content[:200])
        raise AIError("模型这次没给出合法 JSON,可以重试一次")
    return parsed


def _loads_loose(content: str):
    """模型常把 JSON 包在 ```json 里,或者前后带一句废话,都兼容掉。"""
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    m = re.search(r"[{\[][\s\S]*[}\]]", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


# ---------- 清洗 ----------

def _s(v, limit=200):
    if v is None:
        return None
    t = str(v).strip()
    return t[:limit] or None


def _list_of_str(v, *, max_items=6, limit=200):
    if not isinstance(v, list):
        return []
    out = []
    for x in v[:max_items]:
        t = _s(x, limit)
        if t:
            out.append(t)
    return out


def _valid_date(s) -> bool:
    try:
        datetime.strptime(str(s), _DATE_FMT)
        return True
    except (TypeError, ValueError):
        return False


def _coord(v, limit):
    """解析经纬度并做范围校验。limit=90 给纬度,180 给经度。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if -limit <= f <= limit else None


def clean_outline(raw, *, shift_to_future: bool = False) -> dict:
    """骨架清洗。日期不合法 / 天数对不上就直接报错——后面每一步都依赖它。

    shift_to_future:用户没给日期、由模型自己拟日期时打开。模型对"今天"没有
    可靠概念,经常按训练时的年份排(2026 年了还排 2025 年的行程)。提示词里
    已经写明今天是哪天,这里再兜一道:整段往后挪整年直到落在今天之后。
    只按年挪,保住模型挑的月份和星期几——"十月看极光"不能被改成别的月份。
    """
    if not isinstance(raw, dict):
        raise AIError("模型返回的不是行程对象")
    start, end = _s(raw.get("start_date"), 10), _s(raw.get("end_date"), 10)
    if not (_valid_date(start) and _valid_date(end)):
        raise AIError("模型没给出合法的起止日期")
    d0 = datetime.strptime(start, _DATE_FMT).date()
    d1 = datetime.strptime(end, _DATE_FMT).date()
    if d1 < d0:
        raise AIError("结束日期早于开始日期")
    span = (d1 - d0).days + 1

    if shift_to_future and d0 < date.today():
        span_days = (d1 - d0).days
        bump = 0
        while d0.replace(year=d0.year + bump + 1) <= date.today() and bump < 10:
            bump += 1
        try:
            d0 = d0.replace(year=d0.year + bump + 1)
        except ValueError:                 # 2 月 29 日遇上平年
            d0 = d0.replace(year=d0.year + bump + 1, day=28)
        d1 = d0 + timedelta(days=span_days)
        start, end = d0.strftime(_DATE_FMT), d1.strftime(_DATE_FMT)
    if span > MAX_DAYS:
        raise AIError(f"行程超过 {MAX_DAYS} 天,请拆成几段分别生成")

    by_no = {}
    for d in (raw.get("days") or []):
        if not isinstance(d, dict):
            continue
        try:
            n = int(d.get("day_no"))
        except (TypeError, ValueError):
            continue
        if 1 <= n <= span:
            by_no[n] = d

    days = []
    for i in range(span):
        n = i + 1
        src = by_no.get(n, {})
        days.append({
            "day_no": n,
            # 日期一律按起始日推算,不信模型自己填的——它经常跳号或者漏闰
            "date": (d0 + timedelta(days=i)).strftime(_DATE_FMT),
            "route": _s(src.get("route"), 60),
            "transport": _s(src.get("transport"), 120),
            "meal": _s(src.get("meal"), 40),
        })

    return {
        "title": _s(raw.get("title"), 60) or "新的行程",
        "subtitle": _s(raw.get("subtitle"), 120),
        "code": _s(raw.get("code"), 60),
        "cover_note": _s(raw.get("cover_note"), 200),
        # 模型挑的主题色;不在预设里就留空,由调用方兜底
        "accent": (raw.get("accent") if raw.get("accent") in ACCENTS else None),
        "start_date": start,
        "end_date": end,
        "days": days,
    }


_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")


def clean_day_detail(raw) -> dict:
    if not isinstance(raw, dict):
        raise AIError("模型返回的不是当天详情对象")
    out: dict = {}

    sched = []
    for row in (raw.get("sched") or [])[:14]:
        if isinstance(row, dict):
            row = [row.get("time"), row.get("title"), row.get("note"), row.get("key")]
        if not isinstance(row, list) or len(row) < 2:
            continue
        t = _s(row[0], 8)
        title = _s(row[1], 80)
        if not title:
            continue
        item = [t if (t and _TIME_RE.match(t)) else "", title]
        note = _s(row[2], 120) if len(row) > 2 else None
        item.append(note or "")
        item.append(1 if (len(row) > 3 and row[3]) else 0)
        sched.append(item)
    if sched:
        out["sched"] = sched

    # 地点只有一份:stops。没有坐标的也留着——它在地图上不画,但在地点
    # 列表里看得见、能挂照片,之后补上坐标就会出现在地图上。
    # 坐标**不合法**则是另一回事:整个坐标丢掉(点保留),因为地图上一个
    # 错点比少一个点糟得多。
    stops, seen = [], set()
    for st in (raw.get("stops") or [])[:14]:
        if isinstance(st, str):
            st = {"t": st}
        if not isinstance(st, dict):
            continue
        name = _s(st.get("t") or st.get("name"), 60)
        if not name:
            continue
        lat, lng = _coord(st.get("lat"), 90), _coord(st.get("lng"), 180)
        if lat is None or lng is None:
            lat = lng = None
        key = (name, None if lat is None else round(lat, 4),
               None if lng is None else round(lng, 4))
        if key in seen:
            continue
        seen.add(key)
        item = {"t": name}
        if lat is not None:
            item["lat"], item["lng"] = round(lat, 6), round(lng, 6)
        dur = _s(st.get("dur"), 40)
        if dur:
            item["dur"] = dur
        if st.get("air"):
            item["air"] = 1
        if st.get("sea"):
            item["sea"] = 1
        desc = _s(st.get("desc"), 400)
        if desc:
            item["desc"] = desc
        stops.append(item)
    if stops:
        out["stops"] = stops

    # 模型(以及历史数据)还会吐 spots,原样并进来,别丢
    out["spots"] = raw.get("spots")
    merge_spots_into_stops(out)

    for k in ("todo", "cam", "buy", "warn"):
        items = _list_of_str(raw.get(k), max_items=5, limit=180)
        if items:
            out[k] = items

    stay = raw.get("stay")
    if isinstance(stay, dict):
        h, a = _s(stay.get("h"), 80), _s(stay.get("a"), 120)
        if h or a:
            s = {"h": h or "", "a": a or ""}
            lat, lng = _coord(stay.get("lat"), 90), _coord(stay.get("lng"), 180)
            if lat is not None and lng is not None:
                s["lat"], s["lng"] = round(lat, 6), round(lng, 6)
            out["stay"] = s

    return out


def clean_block(kind: str, raw) -> dict:
    if not isinstance(raw, dict):
        raise AIError("模型返回的不是对象")
    if kind == "spot_desc":
        text = _s(raw.get("text"), 600)
        if not text:
            raise AIError("模型没给出内容")
        return {"text": text}
    if kind == "packing":
        items = []
        for it in (raw.get("items") or [])[:30]:
            if isinstance(it, str):
                it = {"label": it}
            if not isinstance(it, dict):
                continue
            label = _s(it.get("label"), 60)
            if label:
                items.append({"grp": _s(it.get("grp"), 30) or "其它",
                              "label": label, "hint": _s(it.get("hint"), 120)})
        if not items:
            raise AIError("模型没给出内容")
        return {"items": items}
    if kind == "facts":
        items = []
        for it in (raw.get("items") or [])[:12]:
            if not isinstance(it, dict):
                continue
            label = _s(it.get("label"), 40)
            body = _s(it.get("body"), 800)
            if label and body:
                items.append({"label": label, "body": body})
        if not items:
            raise AIError("模型没给出内容")
        return {"items": items}
    items = _list_of_str(raw.get("items"), max_items=5, limit=180)
    if not items:
        raise AIError("模型没给出内容")
    return {"items": items}


# ---------- 对外 ----------

def gen_outline(*, notice: str | None = None, idea: str | None = None,
                start: str | None = None, end: str | None = None,
                days: int | None = None, llm: dict | None = None) -> dict:
    today = date.today().strftime(_DATE_FMT)
    if notice:
        user = build_outline_from_notice(notice, today)
    elif idea:
        user = build_outline_from_idea(idea, start, end, days, today)
    else:
        raise AIError("没有输入内容")
    from constants import LLM_TIMEOUT_LONG
    raw = _json_call(OUTLINE_SYSTEM, user, endpoint="travel.outline",
                     timeout=LLM_TIMEOUT_LONG, temperature=0.2, llm=llm)
    # 行程单里的日期是白纸黑字写着的(可能是已经走完的行程),不能动;
    # 用户自己给了日期同理。只有"模型自己拟日期"这一种情况才顺延。
    return clean_outline(raw, shift_to_future=not notice and not (start or end))


def gen_day_detail(trip: dict, day: dict, raw_slice: str | None = None,
                   llm: dict | None = None) -> dict:
    from constants import LLM_TIMEOUT_LONG
    raw = _json_call(DAY_SYSTEM, build_day_prompt(trip, day, raw_slice),
                     endpoint="travel.day", timeout=LLM_TIMEOUT_LONG,
                     temperature=0.4, llm=llm)
    return clean_day_detail(raw)


def extract_facts(notice: str, llm: dict | None = None) -> list[dict]:
    """从行程单原文里抽速查信息。

    只抽不编:领队电话、航班号这类是原文才有的事实,编一个像模像样的假号码
    比没有糟得多。原文里没有就返回空列表,由用户自己填或者单独点 AI 起草
    (那条路走的是常识性信息:时差、货币、插头)。
    """
    from constants import LLM_TIMEOUT_LONG
    raw = _json_call(FACTS_EXTRACT_SYSTEM, build_facts_extract_prompt(notice),
                     endpoint="travel.facts_extract", timeout=LLM_TIMEOUT_LONG,
                     temperature=0.1, llm=llm)
    if not isinstance(raw, dict):
        return []
    out = []
    for it in (raw.get("items") or [])[:12]:
        if not isinstance(it, dict):
            continue
        label, body = _s(it.get("label"), 40), _s(it.get("body"), 800)
        if label and body:
            out.append({"label": label, "body": body})
    return out


def gen_spot_descs(trip: dict, day: dict, names: list[str],
                   llm: dict | None = None) -> dict[str, str]:
    """一次给一天的地点批量写介绍。

    按天而不是按点调用:一趟十四天六七十个点,一个点一次调用又慢又贵,
    而且模型看不到当天的上下文。按天来,一次十来个点,还能顺着当天的
    主线写得连贯些。

    @returns {地点名: 介绍}。模型没认出来的点不会出现在结果里。
    """
    from constants import LLM_TIMEOUT_LONG
    if not names:
        return {}
    raw = _json_call(SPOT_DESCS_SYSTEM, build_spot_descs_prompt(trip, day, names),
                     endpoint="travel.spot_descs", timeout=LLM_TIMEOUT_LONG,
                     temperature=0.5, llm=llm)
    out: dict[str, str] = {}
    if not isinstance(raw, dict):
        return out
    wanted = {n: n for n in names}
    for it in (raw.get("items") or [])[:20]:
        if not isinstance(it, dict):
            continue
        name = _s(it.get("t") or it.get("name"), 60)
        desc = _s(it.get("desc"), 400)
        # 名字对不上就丢掉:写回去要按名字配对,配错了比没有还糟
        if name and desc and name in wanted:
            out[name] = desc
    return out


def gen_block(kind: str, ctx: dict, llm: dict | None = None) -> dict:
    if kind not in BLOCK_KINDS:
        raise AIError(f"不支持的生成类型:{kind}")
    # 和其它生成一样用 LLM_TIMEOUT_LONG。原来写死 60 秒:打包清单和速查要吐
    # 十几二十条 JSON,共享端点高峰期根本跑不完,表现就是点了没反应。
    from constants import LLM_TIMEOUT_LONG
    system, user = build_block_prompt(kind, ctx)
    raw = _json_call(system, user, endpoint=f"travel.block.{kind}",
                     timeout=LLM_TIMEOUT_LONG, temperature=0.6, llm=llm)
    return clean_block(kind, raw)


def slice_notice(notice: str, day: dict) -> str | None:
    """从行程单原文里粗略截出某一天的段落,喂给按天细化那一步。

    只按「第 N 天 / DN / D1」这类行首标记切;切不出来就返回 None,
    让模型按主线自由发挥——比把整份 12000 字原文每天重发一遍省得多。
    """
    if not notice:
        return None
    n = day.get("day_no")
    pat = re.compile(rf"^[^\n]*(?:第\s*{n}\s*天|\bD\s*{n}\b|Day\s*{n}\b)", re.M | re.I)
    m = pat.search(notice)
    if not m:
        return None
    nxt = re.compile(rf"^[^\n]*(?:第\s*{n + 1}\s*天|\bD\s*{n + 1}\b|Day\s*{n + 1}\b)", re.M | re.I)
    m2 = nxt.search(notice, m.end())
    return notice[m.start(): m2.start() if m2 else min(len(notice), m.start() + 4000)]
