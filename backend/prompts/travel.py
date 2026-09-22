"""行程 AI 生成的提示词。

拆成三层,是因为一次调用做不出一份完整行程:
  1. OUTLINE —— 只抽骨架(标题 / 起止 / 每天一句主线),输出小、好校验
  2. DAY     —— 按天细化,每天一次调用,单次输出可控,失败只需重跑那一天
  3. BLOCK   —— 单块重写(某个景点的介绍、某天的贴士…),给人工编辑当草稿

所有输出都要求严格 JSON:解析失败可以重试或丢弃,不会把半截文本写进库。
"""

_JSON_RULE = (
    "只输出 JSON,不要 markdown 代码块、不要任何解释文字。"
    "不确定的字段给 null 或空数组,不要编造具体的航班号、门票价格、营业时间。"
)

# ---------- 1. 骨架 ----------

OUTLINE_SYSTEM = (
    "你是一个行程整理助手,把旅行社行程单或一句话想法整理成结构化的行程骨架。\n"
    + _JSON_RULE + "\n"
    "输出结构:\n"
    '{"title":"行程名","subtitle":"一句副标题或 null","code":"团号或 null",'
    '"cover_note":"一两句这趟的看点或 null",'
    '"accent":"glacier|aurora|ember|sakura|desert|violet",'
    '"start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD",'
    '"days":[{"day_no":1,"date":"YYYY-MM-DD","route":"上海 → 赫尔辛基",'
    '"transport":"HO1607 PVG–HEL 09:05/14:00 或 null","meal":"早 / 午 或 null"}]}\n'
    "规则:\n"
    "- route 是当天主线,城市之间用 → ,不超过 20 字\n"
    "- transport 写航班号 / 车程 / 船班这类一句话说明\n"
    "- meal 只写当天含的餐,如「早 / 午」\n"
    "- days 必须覆盖 start_date 到 end_date 的每一天,day_no 从 1 连续不跳号\n"
    "- 日期一律 YYYY-MM-DD\n"
    "- cover_note 是打开行程时最上面那句话,写这趟最值得期待的是什么,不超过 40 字\n"
    "- accent 按这趟行程的气质挑一个主题色:\n"
    "  glacier 冰川蓝(极地 / 雪山 / 北欧)、aurora 极光绿(极光 / 森林 / 湖区)、\n"
    "  ember 余烬橙(沙漠 / 秋色 / 古城)、sakura 樱粉(日本 / 春季 / 海岛度假)、\n"
    "  desert 沙金(中东 / 非洲 / 戈壁)、violet 夜紫(都市 / 夜景 / 音乐节)"
)


def build_outline_from_notice(text: str, today: str) -> str:
    return (
        f"今天是 {today}。\n"
        "下面是一份旅行社行程单的原文,把它整理成行程骨架。\n"
        "原文里有的信息照抄,没有的留 null,不要自己补。\n"
        "原文里的日期如果只写了月日没写年份,按今天往后最近的那一年算。\n\n"
        f"```\n{text[:12000]}\n```"
    )


def build_outline_from_idea(idea: str, start: str | None, end: str | None,
                            days: int | None, today: str) -> str:
    hint = []
    if start:
        hint.append(f"出发日期 {start}")
    if end:
        hint.append(f"返程日期 {end}")
    if days:
        hint.append(f"共 {days} 天")
    tail = ("已知:" + "、".join(hint) + "。") if hint else ""
    return (
        f"**今天是 {today}**。排日期时务必以这个为准,不要用你印象里的"
        "\"今年\"——那多半是过去的年份了。\n"
        "我想去旅行,下面是我的想法。请排一份合理的行程骨架:\n"
        f"「{idea[:2000]}」\n{tail}\n"
        "按常见的玩法安排每天的主线城市和交通方式,不要把一天排得太满。\n"
        f"如果我没给日期,就从 {today} 之后挑一个合适的时间起算"
        "(比如我提到了某个季节,就取今天之后最近的那一次),"
        "并在 subtitle 里说明这是建议日期。"
    )


# ---------- 2. 按天细化 ----------

DAY_SYSTEM = (
    "你是一个行程细化助手,把某一天的安排展开成结构化内容。\n"
    + _JSON_RULE + "\n"
    "输出结构:\n"
    '{"sched":[["08:00","酒店早餐","可选备注或省略",0]],'
    '"stops":[{"t":"地点名","dur":"停留时长","lat":60.173,"lng":24.925,'
    '"air":0,"sea":0,"desc":"一到两句介绍"}],'
    '"todo":["值得做的事"],"cam":["拍摄建议"],"buy":["买什么"],"warn":["注意事项"],'
    '"stay":{"h":"酒店名或 null","a":"地址或 null","lat":null,"lng":null}}\n'
    "规则:\n"
    "- sched 第 4 位是 1 表示当天的重点,其余写 0;时间用 24 小时制 HH:MM\n"
    "- stops 是当天去的地点,按先后顺序,景点、机场、集合点都算\n"
    "- 经纬度用 WGS-84,**只填你确实知道的坐标,拿不准就把 lat/lng 留空**\n"
    "  ——地图上一个错点比少一个点糟得多;没坐标的地点照样保留,只是不画在地图上\n"
    "- air=1 表示这一段是飞过去的,sea=1 表示坐船\n"
    "- todo / cam / buy / warn 各写 0~4 条,每条一句话,写具体的、当地的,\n"
    "  不要「注意安全」「带好证件」这种放之四海皆准的废话\n"
    "- 原文里没提到的酒店不要编,stay 给 null"
)


def build_day_prompt(trip: dict, day: dict, raw: str | None) -> str:
    head = (
        f"行程:{trip.get('title') or ''} {trip.get('subtitle') or ''}\n"
        f"第 {day.get('day_no')} 天 · {day.get('date') or ''}\n"
        f"当天主线:{day.get('route') or '(未填)'}\n"
        f"交通:{day.get('transport') or '(未填)'}\n"
        f"含餐:{day.get('meal') or '(未填)'}\n"
    )
    if raw:
        return head + "\n这一天在原始行程单里的相关段落:\n```\n" + raw[:4000] + "\n```\n请据此展开。"
    return head + "\n没有原文,请按这条主线安排一天合理的内容。"


# ---------- 2.5 从行程单里抽速查 ----------

FACTS_EXTRACT_SYSTEM = (
    "你从旅行社行程单里**抽取**速查信息,注意是抽取,不是创作。\n"
    + _JSON_RULE + "\n"
    '输出结构:{"items":[{"label":"标题","body":"正文,可多行"}]}\n'
    "规则:\n"
    "- **只抽原文里明确写了的**。领队姓名电话、集合时间地点、航班号与起降时间、\n"
    "  团号、使馆电话、退税节点、硬性规定——原文有就抽,原文没有就不要这一条。\n"
    "- 一个字都不许编。宁可只返回一条,也不要靠常识补全一个像模像样的电话或航班号。\n"
    "- 原文里一条都没有就返回 {\"items\":[]}。\n"
    "- body 写纯文本,多行用换行分隔,不要 HTML 和 markdown 表格。\n"
    "- 同类信息合并成一条,比如四个航班段合成一条「航班」。"
)


def build_facts_extract_prompt(notice: str) -> str:
    return (
        "从下面这份行程单里抽出速查信息。再强调一次:原文没写的一条都不要出现。\n\n"
        f"```\n{notice[:12000]}\n```"
    )


# ---------- 2.6 批量补景点介绍 ----------

SPOT_GEOS_SYSTEM = (
    "你给旅行行程里的地点标经纬度。\n"
    + _JSON_RULE + "\n"
    '输出结构:{"items":[{"i":1,"t":"地点名(照抄我给的)",'
    '"lat":60.1725,"lng":24.9255,"place":"你确认到的地方全名","sure":1}]}\n'
    "规则:\n"
    "- i 是我给的那个编号,**必须带上**:名字你可能会写成别的样子,编号不会错\n"
    "- 坐标用 WGS-84,小数点后 4 位以上\n"
    "- place 写你认为这是哪儿的全名(含城市 / 国家),让用户能核对是不是同一个地方\n"
    "- 名气不大的餐馆、连锁店的某一家分店、同名的地方,拿不准就 sure 写 0;\n"
    "  实在不知道就 lat/lng 都给 null,**不要猜一个大概的城市中心糊弄过去**\n"
    "- 我给了当天的路线,同名的地方据此消歧(比如选路线上的那个城市)\n"
    "- 每个地点都要回一条,包括你不知道的那些(给 null)"
)


SPOT_DESCS_SYSTEM = (
    "你给旅行行程里的地点写简介。\n"
    + _JSON_RULE + "\n"
    '输出结构:{"items":[{"i":1,"t":"地点名(照抄我给的)","desc":"介绍"}]}\n'
    "规则:\n"
    "- i 是我给的那个编号,**必须带上**:名字你可能会写成别的样子,编号不会错\n"
    "- 每条 50~120 字:这是什么、为什么值得来、看什么最好。口语一点,不要宣传腔\n"
    "- 不要写门票价格、营业时间、电话——这些会过期,也不是你能确定的\n"
    "- 机场、码头、服务区这种纯交通节点,一句话说清它在行程里的作用就够\n"
    "- 不认识的地点就**不要**放进 items,宁可少给几条也不要编"
)


def build_spot_geos_prompt(trip: dict, day: dict, names: list[str]) -> str:
    return (
        f"行程:{trip.get('title') or ''} {trip.get('subtitle') or ''}\n"
        f"第 {day.get('day_no')} 天 · {day.get('date') or ''} · "
        f"{day.get('route') or ''}\n\n"
        "给下面这些地点各标一个经纬度。每条回复里带上前面的编号 i:\n"
        + "\n".join(f"{i}. {n}" for i, n in enumerate(names[:14], 1))
    )


def build_spot_descs_prompt(trip: dict, day: dict, names: list[str]) -> str:
    return (
        f"行程:{trip.get('title') or ''} {trip.get('subtitle') or ''}\n"
        f"第 {day.get('day_no')} 天 · {day.get('date') or ''} · "
        f"{day.get('route') or ''}\n\n"
        "给下面这些地点各写一条介绍。每条回复里带上前面的编号 i:\n"
        + "\n".join(f"{i}. {n}" for i, n in enumerate(names[:12], 1))
    )


# ---------- 3. 单块重写 ----------

BLOCK_SYSTEM = (
    "你是一个旅行内容助手,给出的是**草稿**,用户会自己改。\n"
    + _JSON_RULE
)

_BLOCK_SPECS = {
    "spot_desc": (
        '{"text":"..."}',
        "写一段 60~140 字的景点介绍:它是什么、为什么值得来、看什么最好。"
        "口语一点,不要旅游宣传腔,不要罗列门票和营业时间。",
    ),
    "day_tips": (
        '{"items":["...","..."]}',
        "写 3~4 条当天值得做的事,每条一句话,要具体到这个地方,"
        "不要「注意安全」这种到哪儿都适用的废话。",
    ),
    "day_cam": (
        '{"items":["...","..."]}',
        "写 2~3 条当天的拍摄建议:什么机位、什么光线、什么时间。",
    ),
    "day_buy": (
        '{"items":["...","..."]}',
        "写 2~3 条当地值得买的东西,带上在哪买更便宜这类实际信息。",
    ),
    "day_warn": (
        '{"items":["...","..."]}',
        "写 2~3 条当天真正需要留意的事,比如时间紧、要提前换票、天气。",
    ),
    "spot_geo": (
        '{"lat":60.1725,"lng":24.9255,"place":"确认到的地方全名","sure":1}',
        "给出这个地点的经纬度(WGS-84,小数点后 4 位以上)。\n"
        "- place 写你认为这是哪儿的全名(含城市 / 国家),让用户能核对是不是同一个地方\n"
        "- 名气不大的餐馆、连锁店的某一家分店、同名的地方,拿不准就 sure 写 0;\n"
        "  实在不知道就 lat/lng 都给 null,**不要猜一个大概的城市中心糊弄过去**\n"
        "- 有当天路线和行程信息时据此消歧(比如同名的城市选路线上的那个)",
    ),
    # 批量定位不走 _BLOCK_SPECS 的提示词(它有自己的 SPOT_GEOS_SYSTEM),
    # 放在这里只是为了让它成为一个合法的 block kind
    "spot_geos": ("(见 SPOT_GEOS_SYSTEM)", "批量给地点标经纬度。"),
    "packing": (
        '{"items":[{"grp":"分组","label":"物品","hint":"一句说明或 null"}]}',
        "按这趟行程的目的地、季节和活动,列一份打包清单,12~24 条,按分组归类。",
    ),
    "facts": (
        '{"items":[{"label":"标题","body":"正文,可多行"}]}',
        "列几条这趟行程的速查信息:时差、货币与支付、插头、退税、气温参考、硬性规定。"
        "不要编造领队电话、航班号这类只有行程单才有的信息。",
    ),
}

BLOCK_KINDS = tuple(_BLOCK_SPECS)


def build_block_prompt(kind: str, ctx: dict) -> tuple[str, str]:
    """@returns (system, user)"""
    shape, task = _BLOCK_SPECS[kind]
    system = f"{BLOCK_SYSTEM}\n输出结构:{shape}"
    lines = [task, ""]
    if ctx.get("trip"):
        t = ctx["trip"]
        lines.append(f"行程:{t.get('title') or ''} {t.get('subtitle') or ''}"
                     f"({t.get('start_date')} ~ {t.get('end_date')})")
    if ctx.get("day"):
        d = ctx["day"]
        lines.append(f"这一天:第 {d.get('day_no')} 天 · {d.get('date') or ''} · {d.get('route') or ''}")
    if ctx.get("spot"):
        lines.append(f"地点:{ctx['spot']}")
    if ctx.get("hint"):
        lines.append(f"用户补充:{ctx['hint'][:500]}")
    return system, "\n".join(x for x in lines if x)
