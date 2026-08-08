"""Anon 助手小贴士端点 — 调 LLM 生成一句 ≤ 20 字的随机贴士。

仅 sidebar 装饰用，不影响业务流程；LLM 失败时回退到本地静态池。
"""
from __future__ import annotations

import logging
import random
from flask import Blueprint, g, jsonify

from auth import login_required
from services.llm_config import get_llm_config

tips_bp = Blueprint("tips", __name__)

logger = logging.getLogger(__name__)

# 本地兜底池：LLM 不可用或配额不足时随机抽一条
_FALLBACK_TIPS = [
    "今天也要好好记账哦 🌱",
    "小额日常累积起来很惊人～",
    "每月看一眼月度报告吧 📑",
    "设个理财目标更有方向感 🎯",
    "记得定期备份你的账本 💾",
    "检查一下本月预算还剩多少？",
    "🌴 投资理财，长期主义最香",
    "咖啡也要记一笔 ☕",
    "周末是回顾本周开销的好时机",
    "意外支出最容易破财，提前留点缓冲～",
]


@tips_bp.route("/api/anon/tip", methods=["GET"])
@login_required
def get_tip():
    """生成一句 ≤ 20 字的随机财务小贴士。

    走用户配置的 LLM provider；若用户没配 LLM key 或调用失败，回退到
    本地随机池，永远 200。
    """
    llm_cfg = get_llm_config(g.user_id) or {}
    api_key = llm_cfg.get("apikey")
    # 没配 key 直接走 fallback，免去白调一次失败
    if not api_key:
        return jsonify({"tip": random.choice(_FALLBACK_TIPS), "source": "fallback"})

    try:
        from services.llm import _call_llm
        # temperature 高一点保证每次不一样；timeout 短，慢就 fallback
        result = _call_llm(
            messages=[
                {"role": "system", "content":
                    "你是「智能记账助手 Anon」，给用户来一句不超过 20 字的小贴士。"
                    "可以是理财建议、记账技巧、生活感悟，活泼可爱带 1 个 emoji。"
                    "只回复一句，不要解释，不要引号。"},
                {"role": "user", "content": "再给我一句吧"},
            ],
            llm=llm_cfg,
            temperature=1.0,
            timeout=8,
            endpoint="anon.tip",
        )
        if result and "choices" in result:
            text = (result["choices"][0]["message"].get("content") or "").strip()
            # 去掉外层引号 / 长度截断
            text = text.strip('"“”「」 \n')
            if 1 <= len(text) <= 40:
                return jsonify({"tip": text, "source": "llm"})
    except Exception as e:  # noqa: BLE001
        logger.debug("Anon tip LLM 失败，回退本地池：%s", e)

    return jsonify({"tip": random.choice(_FALLBACK_TIPS), "source": "fallback"})
