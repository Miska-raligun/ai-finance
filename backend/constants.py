# 分类类型常量
CATEGORY_EXPENSE = "支出"
CATEGORY_INCOME = "收入"

# 参数名常量
PARAM_CATEGORY = "分类"
PARAM_NOTE = "备注"
PARAM_AMOUNT = "金额"
PARAM_DATE = "时间"
PARAM_MONTH = "月份"

# 默认 LLM 配置
DEFAULT_LLM_URL = "https://api.siliconflow.cn/v1/chat/completions"
DEFAULT_LLM_MODEL = "deepseek-ai/DeepSeek-V4-Pro"
DEFAULT_PERSONA = "一个有点傲娇的财务顾问"

# LLM 请求超时(秒,非流式:要等整段生成完才返回)。
# 财务体检 / 购前决策这类要输出一大段结构化 JSON 的端点用 LLM_TIMEOUT_LONG;
# 共享 DeepSeek 端点高峰期慢,默认给到 60s 避免生成没完就被判超时退本地规则。
# 换更快的自建/付费端点后可在 .env 里调低。
import os as _os
LLM_TIMEOUT_LONG = int(_os.getenv("LLM_TIMEOUT_LONG", "60"))
