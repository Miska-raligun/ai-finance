import os
import logging
import requests
from datetime import datetime
from constants import DEFAULT_LLM_URL, DEFAULT_LLM_MODEL, DEFAULT_PERSONA

logger = logging.getLogger(__name__)

llm_logger = logging.getLogger("llm_return")
llm_logger.setLevel(logging.INFO)
if not llm_logger.handlers:
    handler = logging.FileHandler("llm_return.log", encoding="utf-8")
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    llm_logger.addHandler(handler)


def _call_llm(
    messages: list[dict],
    llm: dict | None = None,
    tools: list | None = None,
    tool_choice: str | None = None,
    temperature: float = 0.3,
    timeout: int = 10,
) -> dict | None:
    """统一 LLM API 调用，返回完整 response JSON 或 None"""
    llm = llm or {}
    api_key = llm.get("apikey") or os.getenv("DEEPSEEK_API_KEY")
    url = llm.get("url") or DEFAULT_LLM_URL
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload: dict = {
        "model": llm.get("model") or DEFAULT_LLM_MODEL,
        "temperature": temperature,
        "messages": messages,
    }
    if tools:
        payload["tools"] = tools
    if tool_choice:
        payload["tool_choice"] = tool_choice

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=timeout)
        data = res.json()
        if "error" in data:
            logger.error("LLM API 错误：%s", data["error"])
            return None
        return data
    except Exception as e:
        logger.error("LLM 调用失败: %s", e)
        return None


def call_llm_intent(message: str, llm: dict | None = None, finance_tools: list | None = None) -> dict | None:
    """意图识别（带工具调用）"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    messages = [
        {"role": "system", "content": f"今天是 {today_str}。你是智能财务助手，根据用户输入调用合适的工具完成记账操作。用户有多个操作时可同时调用多个工具。闲聊时不调用工具。"},
        {"role": "user", "content": message},
    ]
    return _call_llm(
        messages, llm=llm, tools=finance_tools, tool_choice="auto", temperature=0.3, timeout=10,
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
    result = _call_llm(messages, llm=llm, timeout=30)
    if result and "choices" in result:
        return result["choices"][0]["message"]["content"]
    if result and "error" in result:
        logger.error("DeepSeek API error: %s", result["error"])
        return "❌ 分析失败：" + result["error"].get("message", "未知错误")
    return "⚠️ 暂时无法获取 AI 总结，请稍后重试"


def call_llm_chat(history: list[dict], llm: dict | None = None) -> str:
    """当用户没有执行记账相关操作时，与其闲聊。"""
    llm = llm or {}
    persona = llm.get("persona") or DEFAULT_PERSONA
    prompt = (
        f"你是{persona}，你的名字叫Anon。可以和用户闲聊，并在合适的时候提醒保持良好的记账习惯。\n"
        "回答控制在50字以内。"
    )
    messages = [{"role": "system", "content": prompt}] + history[-10:]
    result = _call_llm(messages, llm=llm, timeout=10)
    if result and "choices" in result:
        return result["choices"][0]["message"]["content"]
    return "⚠️ 暂时无法回复"


def call_llm_budget_advice(prompt: str, llm: dict | None = None) -> str:
    """预算建议 LLM 调用（供 handlers.py 使用）"""
    messages = [{"role": "user", "content": prompt}]
    result = _call_llm(messages, llm=llm, temperature=0.5, timeout=60)
    if result is None:
        raise RuntimeError("预算推荐 API 调用失败")
    if "choices" not in result:
        raise RuntimeError(f"预算推荐 API 响应异常：{result.get('error', result)}")
    return result["choices"][0]["message"]["content"]
