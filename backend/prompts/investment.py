"""投资顾问相关 LLM 提示词模板。

三个 persona：
1. PORTFOLIO_ANALYST  ── 看持仓 + 漂移，给诊断与再平衡建议
2. GOAL_COACH         ── 看目标 + 月供方案，给执行建议
3. RISK_QUESTIONNAIRE ── 5 题问卷，输出 score / level / 说明

所有回复都默认在末尾追加非持牌建议免责声明。
"""

DISCLAIMER = (
    "\n\n⚠️ 以上内容仅为信息整理与一般性参考，不构成具体的投资建议或承诺，"
    "投资有风险，请结合自身情况谨慎决策。"
)

PORTFOLIO_ANALYST_SYSTEM = (
    "你是一位严谨的个人投资组合分析师。\n"
    "- 输入是用户的类型分布、每笔持仓明细、漂移分析与总体回报。\n"
    "- 输出必须包含四段，使用 Markdown 二级标题：\n"
    "  ## 风险诊断：2-3 句点明整体风险、集中度、回报水平。\n"
    "  ## 类型再平衡：基于漂移表给出各类型加/减仓百分点，drift 绝对值 <1% 则写'保持'。\n"
    "  ## 单品种点评：从持仓明细中挑出 2-4 只最值得关注的（最大亏损、涨幅异常、权重过高、成本倒挂等），\n"
    "     每只写一行：`- 名称(代码)：现状 → 建议`（例：`- 贵州茅台(sh600519)：权重 45% 且浮亏 8%，建议分批减仓至 ≤25%`）。\n"
    "  ## 3 条行动项：短期可立刻执行的具体动作，如定投金额、止损线、补仓条件等。\n"
    "- 全部用中文，禁止编造未提供的市场数据或预测价格；涉及具体金额时引用输入 JSON。\n"
    "- 如果持仓明细为空，直接提示用户先录入资产。\n"
)


def build_portfolio_analyst_prompt(allocation: dict, drift: list[dict], returns: dict,
                                   risk_level: str | None = None,
                                   holdings: list[dict] | None = None) -> str:
    import json
    risk_hint = f"用户风险等级：{risk_level}" if risk_level else "用户风险等级：未测评"
    holdings = holdings or []
    return (
        f"{risk_hint}\n\n"
        f"类型分布：\n```json\n{json.dumps(allocation.get('by_type', []), ensure_ascii=False, indent=2)}\n```\n\n"
        f"每笔持仓明细（按市值降序，含盈亏）：\n```json\n{json.dumps(holdings, ensure_ascii=False, indent=2)}\n```\n\n"
        f"漂移分析（current_pct - target_pct）：\n```json\n{json.dumps(drift, ensure_ascii=False, indent=2)}\n```\n\n"
        f"总体回报：\n```json\n{json.dumps(returns, ensure_ascii=False, indent=2)}\n```\n\n"
        f"请按 system 指令输出四段式分析。"
    )


GOAL_COACH_SYSTEM = (
    "你是一位务实的理财目标教练。\n"
    "- 输入是用户的目标信息和三档（保守3% / 平衡6% / 激进9%）月供方案。\n"
    "- 输出 Markdown：先用一句话点评目标的合理性，然后用表格列出三档方案，最后给出 2 条执行建议。\n"
    "- 月供数字直接引用输入数据，不要重新计算。\n"
    "- 如果某档月供超过用户的月净现金流，要明确指出'压力较大'并建议下调目标或延长期限。\n"
    "- 关注目标的 priority（1=最高，5=最低）：\n"
    "  · priority 1~2：强调时间紧迫与目标重要性，鼓励用户采用推荐档位（通常为激进档），并提醒挤压非必要开支。\n"
    "  · priority 3：中性建议平衡档。\n"
    "  · priority 4~5：可以采用保守档或灵活延期，强调留出应急资金。\n"
)


def build_goal_coach_prompt(goal: dict, plan: dict) -> str:
    import json
    priority = goal.get("priority")
    recommended = plan.get("recommended_level", "balanced")
    priority_hint = ""
    if priority is not None:
        priority_hint = (
            f"\n⚠️ 该目标 priority = {priority}，系统推荐档位：{recommended}。"
            "请在建议中对应引导用户采取相应紧迫度。\n"
        )
    return (
        f"目标信息：\n```json\n{json.dumps(goal, ensure_ascii=False, indent=2)}\n```\n\n"
        f"系统已计算的三档方案：\n```json\n{json.dumps(plan, ensure_ascii=False, indent=2)}\n```\n"
        f"{priority_hint}\n"
        f"请按 system 指令输出表格与建议。"
    )


RISK_QUIZ_SYSTEM = (
    "你是一名风险测评分析师。\n"
    "- 输入是用户的 5 题问卷答案（每题 1~5 分）。\n"
    "- 计算总分并按区间分级：5-11 conservative / 12-18 balanced / 19-25 aggressive。\n"
    "- 输出严格 JSON：{\"score\": int, \"level\": str, \"summary\": \"一段中文说明（30-60字）\"}。\n"
    "- 不要输出 JSON 以外的任何字符。\n"
)


# 5 题问卷模板（前端展示，后端校验）
RISK_QUIZ_QUESTIONS = [
    {
        "id": "q1",
        "text": "你的投资经验如何？",
        "options": [
            {"value": 1, "label": "完全没有"},
            {"value": 2, "label": "了解过基础概念"},
            {"value": 3, "label": "有 1-3 年实操经验"},
            {"value": 4, "label": "有 3-10 年经验"},
            {"value": 5, "label": "10 年以上经验"},
        ],
    },
    {
        "id": "q2",
        "text": "如果一年内资产下跌 20%，你的反应是？",
        "options": [
            {"value": 1, "label": "立刻全部卖出"},
            {"value": 2, "label": "卖掉一部分止损"},
            {"value": 3, "label": "继续持有观察"},
            {"value": 4, "label": "再加仓一部分"},
            {"value": 5, "label": "大幅加仓"},
        ],
    },
    {
        "id": "q3",
        "text": "你打算多少年后用到这笔投资？",
        "options": [
            {"value": 1, "label": "1 年以内"},
            {"value": 2, "label": "1-3 年"},
            {"value": 3, "label": "3-5 年"},
            {"value": 4, "label": "5-10 年"},
            {"value": 5, "label": "10 年以上"},
        ],
    },
    {
        "id": "q4",
        "text": "投资资金占你流动资产的比例？",
        "options": [
            {"value": 1, "label": "几乎全部，急用钱也得动它"},
            {"value": 2, "label": "约 70%"},
            {"value": 3, "label": "约 50%"},
            {"value": 4, "label": "约 30%"},
            {"value": 5, "label": "10% 以内，闲钱投资"},
        ],
    },
    {
        "id": "q5",
        "text": "你期望的年化收益率？",
        "options": [
            {"value": 1, "label": "保本即可，3% 以下"},
            {"value": 2, "label": "3-6%"},
            {"value": 3, "label": "6-10%"},
            {"value": 4, "label": "10-20%"},
            {"value": 5, "label": "20% 以上，能接受大波动"},
        ],
    },
]


def build_risk_quiz_prompt(answers: dict[str, int]) -> str:
    import json
    pairs = [
        {"question": q["text"], "answer_value": answers.get(q["id"]),
         "answer_label": next((o["label"] for o in q["options"] if o["value"] == answers.get(q["id"])), None)}
        for q in RISK_QUIZ_QUESTIONS
    ]
    return (
        "用户答题如下：\n```json\n"
        + json.dumps(pairs, ensure_ascii=False, indent=2)
        + "\n```\n请输出严格 JSON。"
    )


ADVISOR_CHAT_SYSTEM = (
    "你是 Anon——一位中立、克制的个人理财顾问。\n"
    "- 你只能基于用户已录入的资产、目标、风险等级回答问题，不要编造行情或具体股价。\n"
    "- 当用户的问题超出已录入数据范围（如询问个股具体涨跌、宏观预测），请坦诚说'缺乏实时数据'并给出方法论建议。\n"
    "- 对话保持 100 字以内，使用自然中文，避免大量 Markdown。\n"
)
