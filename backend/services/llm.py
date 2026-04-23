import os
import logging
import requests
from datetime import datetime
from constants import DEFAULT_LLM_URL, DEFAULT_LLM_MODEL, DEFAULT_PERSONA

logger = logging.getLogger(__name__)

# 为兼容旧调用方，保留 llm_logger 名称；handlers 由 logging_config 统一注册
llm_logger = logging.getLogger("llm_return")
if not llm_logger.handlers:
    # 兜底：未启用集中日志配置时仍写一份本地文件，避免吞日志
    handler = logging.FileHandler("llm_return.log", encoding="utf-8")
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    llm_logger.addHandler(handler)
    llm_logger.setLevel(logging.INFO)


def _record_usage(endpoint: str, model: str, data: dict | None) -> None:
    """把 LLM 返回的 token 用量写入 llm_usage 表，失败静默。"""
    if not data:
        return
    usage = data.get("usage") or {}
    if not usage:
        return
    try:
        from db import get_db
        from flask import g, has_request_context
        user_id = None
        rid = None
        if has_request_context():
            user_id = getattr(g, "user_id", None)
            rid = getattr(g, "request_id", None)
        db = get_db()
        db.execute(
            """
            INSERT INTO llm_usage
              (user_id, endpoint, model, prompt_tokens, completion_tokens, total_tokens, cost_usd, request_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                endpoint,
                model,
                int(usage.get("prompt_tokens") or 0),
                int(usage.get("completion_tokens") or 0),
                int(usage.get("total_tokens") or 0),
                0.0,
                rid,
                datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )
        db.commit()
    except Exception as e:
        logger.debug("LLM usage 记录失败（已忽略）：%s", e)


def _call_llm(
    messages: list[dict],
    llm: dict | None = None,
    tools: list | None = None,
    tool_choice: str | None = None,
    temperature: float = 0.3,
    timeout: int = 10,
    endpoint: str = "unknown",
) -> dict | None:
    """统一 LLM API 调用，返回完整 response JSON 或 None"""
    llm = llm or {}
    api_key = llm.get("apikey") or os.getenv("DEEPSEEK_API_KEY")
    url = llm.get("url") or DEFAULT_LLM_URL
    model = llm.get("model") or DEFAULT_LLM_MODEL
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload: dict = {
        "model": model,
        "temperature": temperature,
        "messages": messages,
    }
    if tools:
        payload["tools"] = tools
    if tool_choice:
        payload["tool_choice"] = tool_choice

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=timeout)
        try:
            data = res.json()
        except ValueError:
            logger.error("LLM 响应非 JSON（endpoint=%s status=%s）：%s",
                         endpoint, res.status_code, (res.text or "")[:500])
            return {"error": {"message": f"HTTP {res.status_code} 非 JSON 响应"}}
        if "error" in data:
            logger.error("LLM API 错误（endpoint=%s status=%s）：%s",
                         endpoint, res.status_code, data["error"])
            return data
        if res.status_code >= 400:
            logger.error("LLM HTTP %s（endpoint=%s）：%s",
                         res.status_code, endpoint, str(data)[:500])
            return {"error": {"message": f"HTTP {res.status_code}"}}
        _record_usage(endpoint, model, data)
        return data
    except requests.exceptions.Timeout:
        logger.error("LLM 调用超时（endpoint=%s timeout=%ss）", endpoint, timeout)
        return {"error": {"message": f"请求超时（{timeout}s）"}}
    except Exception as e:
        logger.error("LLM 调用失败（endpoint=%s）: %s", endpoint, e)
        return {"error": {"message": str(e) or "调用异常"}}


def call_llm_intent(message: str, llm: dict | None = None, finance_tools: list | None = None,
                    extra_system: str | None = None) -> dict | None:
    """意图识别（带工具调用）。extra_system 可注入用户长期画像等上下文。"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    messages = [
        {"role": "system", "content": f"今天是 {today_str}。你是智能财务助手，根据用户输入调用合适的工具完成记账操作。用户有多个操作时可同时调用多个工具。闲聊时不调用工具。"},
    ]
    if extra_system:
        messages.append({"role": "system", "content": extra_system})
    messages.append({"role": "user", "content": message})
    return _call_llm(
        messages, llm=llm, tools=finance_tools, tool_choice="auto", temperature=0.3, timeout=10,
        endpoint="chat.intent",
    )


def call_llm_summary(user_msg: str, handler_result: str, llm: dict | None = None) -> str:
    """操作结果总结"""
    llm = llm or {}
    persona = llm.get("persona") or DEFAULT_PERSONA
    summary_prompt = (
        f"你是{persona}，你的名字叫Anon。请根据用户的操作结果进行总结和建议。\n"
        f"用户输入：{user_msg}\n"
        f"系统执行结果：{handler_result}\n"
        "请用自然语言总结这次操作及执行结果，并提出简短合理的建议（50字以内）,不要添加不必要的格式化符号。\n"
        "当系统执行结果涉及具体数值时，必须保留全部数值，严禁省略！\n"
        "回复尽量人性化且风趣。\n"
        "不要做()括起来的额外回复。\n"
        "如果用户此次操作为本月消费分析请求，给出消费行为详细分析及评分，此时不限制回答字数，必须分别分析当月消费和总体消费，严禁混淆分析！"
    )
    messages = [
        {"role": "system", "content": "你是一个善于总结和分析的财务顾问。"},
        {"role": "user", "content": summary_prompt},
    ]
    result = _call_llm(messages, llm=llm, timeout=30, endpoint="chat.summary")
    if result and "choices" in result:
        return result["choices"][0]["message"]["content"]
    if result and "error" in result:
        logger.error("DeepSeek API error: %s", result["error"])
        return "❌ 分析失败：" + result["error"].get("message", "未知错误")
    return "⚠️ 暂时无法获取 AI 总结，请稍后重试"


def call_llm_chat(history: list[dict], llm: dict | None = None,
                  extra_system: str | None = None) -> str:
    """当用户没有执行记账相关操作时，与其闲聊。"""
    llm = llm or {}
    persona = llm.get("persona") or DEFAULT_PERSONA
    prompt = (
        f"你是{persona}，你的名字叫Anon。可以和用户闲聊，并在合适的时候提醒保持良好的记账习惯。\n"
        "回答控制在50字以内。"
    )
    messages = [{"role": "system", "content": prompt}]
    if extra_system:
        messages.append({"role": "system", "content": extra_system})
    messages += history[-10:]
    result = _call_llm(messages, llm=llm, timeout=10, endpoint="chat.freeform")
    if result and "choices" in result:
        return result["choices"][0]["message"]["content"]
    return "⚠️ 暂时无法回复"


def call_llm_budget_advice(prompt: str, llm: dict | None = None) -> str:
    """预算建议 LLM 调用（供 handlers.py 使用）"""
    messages = [{"role": "user", "content": prompt}]
    result = _call_llm(messages, llm=llm, temperature=0.5, timeout=60, endpoint="budget.advice")
    if result is None:
        raise RuntimeError("预算推荐 API 调用失败")
    if "choices" not in result:
        raise RuntimeError(f"预算推荐 API 响应异常：{result.get('error', result)}")
    return result["choices"][0]["message"]["content"]


# ===== 投资顾问相关 =====

def call_llm_portfolio_advice(allocation: dict, drift: list[dict], returns: dict,
                              risk_level: str | None = None, llm: dict | None = None,
                              holdings: list[dict] | None = None) -> str:
    """Portfolio Analyst：输入持仓 + 漂移 + 回报 + 单品种明细，输出诊断与行动项。"""
    from prompts.investment import (
        PORTFOLIO_ANALYST_SYSTEM, build_portfolio_analyst_prompt, DISCLAIMER,
    )
    messages = [
        {"role": "system", "content": PORTFOLIO_ANALYST_SYSTEM},
        {"role": "user", "content": build_portfolio_analyst_prompt(
            allocation, drift, returns, risk_level, holdings=holdings,
        )},
    ]
    result = _call_llm(messages, llm=llm, temperature=0.4, timeout=60, endpoint="invest.portfolio_advice")
    if result and "choices" in result:
        return result["choices"][0]["message"]["content"] + DISCLAIMER
    if result and "error" in result:
        return f"⚠️ 投资分析失败：{result['error'].get('message', '未知错误')}" + DISCLAIMER
    return "⚠️ 暂时无法获取投资分析，请稍后再试。" + DISCLAIMER


def call_llm_goal_plan(goal: dict, plan: dict, llm: dict | None = None) -> str:
    """Goal Coach：输入目标 + 三档方案，输出 Markdown 表格与建议。"""
    from prompts.investment import GOAL_COACH_SYSTEM, build_goal_coach_prompt, DISCLAIMER
    messages = [
        {"role": "system", "content": GOAL_COACH_SYSTEM},
        {"role": "user", "content": build_goal_coach_prompt(goal, plan)},
    ]
    result = _call_llm(messages, llm=llm, temperature=0.4, timeout=60, endpoint="invest.goal_plan")
    if result and "choices" in result:
        return result["choices"][0]["message"]["content"] + DISCLAIMER
    if result and "error" in result:
        return f"⚠️ 目标方案生成失败：{result['error'].get('message', '未知错误')}" + DISCLAIMER
    return "⚠️ 暂时无法生成目标方案，请稍后再试。" + DISCLAIMER


def call_llm_risk_questionnaire(answers: dict, llm: dict | None = None) -> dict:
    """Risk Questionnaire：输入答案，输出 {score, level, summary}。

    任何解析失败都会回退到本地打分，保证接口稳定。
    """
    import json as _json
    import re as _re
    from prompts.investment import (
        RISK_QUIZ_SYSTEM, RISK_QUIZ_QUESTIONS, build_risk_quiz_prompt,
    )

    # 先本地算分兜底
    try:
        score = sum(int(answers.get(q["id"], 0)) for q in RISK_QUIZ_QUESTIONS)
    except (TypeError, ValueError):
        score = 0
    if score <= 11:
        fallback_level = "conservative"
    elif score <= 18:
        fallback_level = "balanced"
    else:
        fallback_level = "aggressive"

    messages = [
        {"role": "system", "content": RISK_QUIZ_SYSTEM},
        {"role": "user", "content": build_risk_quiz_prompt(answers)},
    ]
    result = _call_llm(messages, llm=llm, temperature=0.2, timeout=20, endpoint="invest.risk_quiz")
    content = ""
    if result and "choices" in result:
        content = result["choices"][0]["message"]["content"] or ""

    parsed = None
    if content:
        try:
            parsed = _json.loads(content)
        except (_json.JSONDecodeError, TypeError):
            m = _re.search(r"\{[\s\S]*\}", content)
            if m:
                try:
                    parsed = _json.loads(m.group(0))
                except _json.JSONDecodeError:
                    parsed = None

    if isinstance(parsed, dict) and parsed.get("level") in {"conservative", "balanced", "aggressive"}:
        return {
            "score": int(parsed.get("score") or score),
            "level": parsed["level"],
            "summary": str(parsed.get("summary") or ""),
        }

    return {
        "score": score,
        "level": fallback_level,
        "summary": "根据你的答题得分，我们给出了默认级别（LLM 解析失败时的本地兜底结果）。",
    }


def call_llm_categorize(note: str, candidates: list[str], llm: dict | None = None) -> str | None:
    """从候选分类中挑出最匹配的一个。temperature=0 提高一致性，最坏返回 None。"""
    if not candidates:
        return None
    cand_str = "/".join(candidates)
    messages = [
        {"role": "system", "content": (
            "你是一名记账分类助手。根据用户的备注内容，从候选分类中精确选择一个最匹配的分类。\n"
            f"候选分类（必须严格从中选择，不能新创建）：{cand_str}\n"
            "仅输出该分类名，不要解释，不要标点，不要 Markdown。\n"
            "如果备注与所有分类都明显不相关，输出 NONE。"
        )},
        {"role": "user", "content": f"备注：{note}"},
    ]
    result = _call_llm(messages, llm=llm, temperature=0.0, timeout=10, endpoint="smart.categorize")
    if not result or "choices" not in result:
        return None
    raw = (result["choices"][0]["message"]["content"] or "").strip()
    raw = raw.strip("「」\"'`. \n")
    if raw == "NONE" or raw not in candidates:
        return None
    return raw


def call_llm_monthly_report(insights: dict, llm: dict | None = None) -> str:
    """生成 Markdown 月度报告。"""
    import json as _json
    period = insights.get("period")
    today_str = datetime.now().strftime("%Y-%m-%d")
    system = (
        "你是一名个人财务顾问。基于以下结构化数据生成中文 Markdown 月度报告。\n"
        f"今天日期是 {today_str}。不要在报告中自行写『生成时间』『报告日期』等字段，"
        "系统会在外层卡片展示时间戳。\n"
        "格式要求：\n"
        "1. 一级标题：「{period} 月度报告」\n"
        "2. 二级章节：① 概览 ② 支出明细 ③ 收入明细 ④ 预算执行 ⑤ 异常提醒 "
        "⑥ 资产与投资 ⑦ 下月建议\n"
        "3. 数字一律保留两位小数，表格用 Markdown 表格语法。\n"
        "4. 概览段必须明确给出净结余金额并指出是结余还是赤字；若有投资组合，\n"
        "   在概览中补充『净资产/总市值=XX，累计浮盈=XX』一句。\n"
        "5. 异常提醒只列举提供的数据，不要编造。\n"
        "6. 「资产与投资」章节要求：\n"
        "   - 若 portfolio.has_portfolio 为 false，写『尚未录入资产，建议从一笔基金或定存开始建立投资档案。』\n"
        "   - 否则列出：总市值 / 总成本 / 累计盈亏金额 + 百分比；类型分布（表格）；"
        "前 5 持仓（表格含名称/持仓/成本价/现值/盈亏%）；重点点评 1-2 只偏离较大的持仓。\n"
        "   - 若 goals 非空，追加『理财目标进度』子表格（名称/目标/已完成/进度%/截止）。\n"
        "7. 下月建议给 3 条具体可执行的行动项；如果有投资组合，至少 1 条涉及资产配置或目标储蓄。\n"
        "8. 不要使用 `---` 或 `***` 等水平分隔线，章节之间用空行和二级标题自然分隔。\n"
        "9. 禁止编造未提供的市场数据或预测价格；金额一律引用输入 JSON。\n"
    ).replace("{period}", str(period))
    user_msg = "数据如下：\n```json\n" + _json.dumps(insights, ensure_ascii=False, indent=2) + "\n```"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]
    result = _call_llm(messages, llm=llm, temperature=0.5, timeout=60, endpoint="smart.monthly_report")
    if result and "choices" in result:
        return result["choices"][0]["message"]["content"]
    return f"# {period} 月度报告\n\n⚠️ 生成失败，请稍后重试。"


def call_llm_profile_extract(history: list[dict], old_facts: dict | None = None,
                             llm: dict | None = None) -> dict | None:
    """从最近对话中提取/合并用户长期事实。返回严格 JSON 字典或 None。"""
    import json as _json
    import re as _re
    snippets = "\n".join(
        f"{m.get('role', '?')}: {(m.get('content') or '')[:200]}" for m in history[-30:]
    )
    old_str = _json.dumps(old_facts or {}, ensure_ascii=False)
    messages = [
        {"role": "system", "content": (
            "你是一名画像构建助手。基于用户与 AI 的对话片段，提取/合并用户的长期事实信息。\n"
            "输出必须是严格 JSON：{\"facts\": {\"income_band\": str|null, \"family_size\": int|null,"
            " \"mortgage\": float|null, \"goals\": [str], \"preferences\": [str], \"risk_tolerance\": str|null}}\n"
            "保留旧 facts 中已有的字段（除非对话中明确推翻）。不能编造。"
        )},
        {"role": "user", "content": f"旧 facts：{old_str}\n\n最近对话片段：\n{snippets}"},
    ]
    result = _call_llm(messages, llm=llm, temperature=0.2, timeout=20, endpoint="smart.profile")
    if not result or "choices" not in result:
        return None
    content = (result["choices"][0]["message"]["content"] or "").strip()
    try:
        return _json.loads(content)
    except _json.JSONDecodeError:
        m = _re.search(r"\{[\s\S]*\}", content)
        if not m:
            return None
        try:
            return _json.loads(m.group(0))
        except _json.JSONDecodeError:
            return None


def call_llm_advisor_chat(history: list[dict], context: dict | None = None, llm: dict | None = None) -> str:
    """投资顾问对话：在 system 中注入用户资产/目标摘要，再接 history。"""
    import json as _json
    from prompts.investment import ADVISOR_CHAT_SYSTEM, DISCLAIMER
    ctx_msg = ""
    if context:
        ctx_msg = "\n\n当前用户数据摘要：\n```json\n" + _json.dumps(context, ensure_ascii=False) + "\n```"
    messages = [{"role": "system", "content": ADVISOR_CHAT_SYSTEM + ctx_msg}] + history[-10:]
    result = _call_llm(messages, llm=llm, temperature=0.5, timeout=30, endpoint="invest.advisor_chat")
    if result and "choices" in result:
        return result["choices"][0]["message"]["content"] + DISCLAIMER
    if result and "error" in result:
        return f"⚠️ 顾问服务失败：{result['error'].get('message', '未知错误')}" + DISCLAIMER
    return "⚠️ 暂时无法回复，请稍后再试。" + DISCLAIMER
