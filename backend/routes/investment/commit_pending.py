"""聊天 / 图片识别得到的待确认资产 / 目标卡片落库 + 图片解析。"""
from __future__ import annotations

import base64
import json

from flask import g, jsonify, request

from auth import login_required

from ._common import investment_bp, load_llm_cfg


@investment_bp.route("/api/investment/commit-asset", methods=["POST"])
@login_required
def commit_asset():
    """确认把聊天/图片识别得到的资产写入数据库。走与直接新增相同的校验与行情自动同步。"""
    data = request.get_json() or {}
    params = {
        "名称": (data.get("name") or "").strip(),
        "类型": (data.get("type") or "other").strip(),
        "代码": (data.get("symbol") or "").strip(),
        "数量": data.get("holdings") or 0,
        "成本": data.get("cost_basis") or 0,
        "现值": data.get("current_value") or 0,
        "备注": (data.get("notes") or "").strip(),
    }
    from handlers import invest_add_asset
    msg = invest_add_asset(g.user_id, params)
    success = msg.startswith("✅")
    status = 200 if success else (409 if "已存在" in msg else 400)
    return jsonify({"success": success, "message": msg}), status


@investment_bp.route("/api/investment/commit-goal", methods=["POST"])
@login_required
def commit_goal():
    data = request.get_json() or {}
    params = {
        "名称": (data.get("name") or "").strip(),
        "目标金额": data.get("target_amount") or 0,
        "截止日期": (data.get("deadline") or "").strip(),
        "已完成": data.get("current_progress") or 0,
        "优先级": data.get("priority") or 3,
        "备注": (data.get("note") or "").strip(),
    }
    from handlers import invest_add_goal
    msg = invest_add_goal(g.user_id, params)
    success = msg.startswith("✅")
    return jsonify({"success": success, "message": msg}), (200 if success else 400)


@investment_bp.route("/api/investment/parse-image", methods=["POST"])
@login_required
def parse_image():
    """上传持仓/目标截图 → MiniMax 识别 → LLM 工具调用 → 返回待确认卡片。"""
    from routes.chat import recognize_image, ALLOWED_IMAGE_TYPES, MAX_IMAGE_SIZE
    from services.llm import call_llm_intent

    if "image" not in request.files:
        return jsonify({"error": "未收到图片文件"}), 400
    file = request.files["image"]
    mime_type = file.content_type
    if mime_type not in ALLOWED_IMAGE_TYPES:
        return jsonify({"error": f"不支持的图片格式：{mime_type}"}), 400
    image_bytes = file.read()
    if len(image_bytes) > MAX_IMAGE_SIZE:
        return jsonify({"error": "图片大小超过 10MB 限制"}), 400

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    recognized = recognize_image(image_b64, mime_type)
    if not recognized:
        return jsonify({"error": "图片识别失败，请重试或手动添加"}), 502

    from tools import FINANCE_TOOLS
    allowed_names = {"invest_add_asset", "invest_add_goal"}
    limited_tools = [t for t in FINANCE_TOOLS if t["function"]["name"] in allowed_names]

    llm_cfg = load_llm_cfg(request.get_json(silent=True) or {})
    prompt = (
        "[图片识别结果] " + recognized + "\n\n"
        "请根据上面内容判断是"
        "①持仓截图（资产、代码、持仓数量、成本、当前市值、类型）"
        "或 ②理财目标截图（目标名称、目标金额、截止日、优先级）。"
        "对于资产：如果不知道市值请留空由系统自动拉取行情；不要自己编造股票/基金代码。"
        "把识别到的每一条调用 invest_add_asset 或 invest_add_goal。"
    )

    response = call_llm_intent(prompt, llm_cfg, limited_tools)
    pending_assets: list[dict] = []
    pending_goals: list[dict] = []
    reply = None
    if response and "choices" in response:
        msg_obj = response["choices"][0].get("message", {})
        tool_calls = msg_obj.get("tool_calls") or []
        for tc in tool_calls:
            name = tc["function"]["name"]
            try:
                params = json.loads(tc["function"]["arguments"])
            except ValueError:
                continue
            if name == "invest_add_asset":
                n = (params.get("名称") or "").strip()
                if not n:
                    continue
                pending_assets.append({
                    "name": n,
                    "type": (params.get("类型") or "other").strip(),
                    "symbol": (params.get("代码") or "").strip(),
                    "holdings": float(params.get("数量", 0) or 0),
                    "cost_basis": float(params.get("成本", 0) or 0),
                    "current_value": float(params.get("现值", 0) or 0),
                    "notes": (params.get("备注") or "").strip(),
                })
            elif name == "invest_add_goal":
                n = (params.get("名称") or "").strip()
                tgt = float(params.get("目标金额", 0) or 0)
                if not n or tgt <= 0:
                    continue
                pending_goals.append({
                    "name": n,
                    "target_amount": tgt,
                    "deadline": (params.get("截止日期") or "").strip(),
                    "current_progress": float(params.get("已完成", 0) or 0),
                    "priority": int(params.get("优先级", 3) or 3),
                    "note": (params.get("备注") or "").strip(),
                })
        if not tool_calls:
            reply = msg_obj.get("content")

    summary_parts = []
    if pending_assets:
        summary_parts.append(f"识别到 {len(pending_assets)} 项资产")
    if pending_goals:
        summary_parts.append(f"识别到 {len(pending_goals)} 项理财目标")
    if not summary_parts:
        reply = reply or "未能识别出可录入的资产或目标，请检查图片或手动添加。"
    else:
        reply = "；".join(summary_parts) + "，请在下方卡片中核对并确认入库。"

    return jsonify({
        "reply": reply,
        "recognized": recognized,
        "pending_assets": pending_assets,
        "pending_goals": pending_goals,
    })
