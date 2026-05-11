"""对话相关路由：文本聊天、图片识别、记录确认"""
import os
import json
import base64
import asyncio
import logging
import threading
from datetime import datetime
from flask import Blueprint, request, jsonify, g
from db import get_db, add_chat_message, get_chat_history
from auth import login_required
from tools import handlers, FINANCE_TOOLS
from services.llm import call_llm_intent, call_llm_summary, call_llm_chat, llm_logger
from constants import PARAM_CATEGORY, PARAM_AMOUNT, PARAM_NOTE, PARAM_DATE

logger = logging.getLogger(__name__)
chat_bp = Blueprint('chat', __name__)


# ── 图片识别 ────────────────────────────────────────────────────
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MIME_TO_EXT = {"image/jpeg": "jpeg", "image/png": "png", "image/webp": "webp"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB

# 全局事件循环（避免每次请求创建新循环）
_loop = asyncio.new_event_loop()
_loop_thread = threading.Thread(target=_loop.run_forever, daemon=True)
_loop_thread.start()


async def _recognize_image_async(image_b64: str, mime_type: str) -> str:
    """通过 MCP 协议调用 MiniMax understand_image 工具"""
    from mcp.client.sse import sse_client
    from mcp import ClientSession

    mcp_port = os.getenv("MINIMAX_MCP_PORT", "5002")
    mcp_url = f"http://localhost:{mcp_port}/sse"
    ext = MIME_TO_EXT.get(mime_type, "jpeg")
    data_url = f"data:image/{ext};base64,{image_b64}"

    async with sse_client(mcp_url) as (read, write):
        async with ClientSession(read, write) as sess:
            await sess.initialize()
            result = await sess.call_tool("understand_image", {
                "prompt": "请识别这张图片中的消费或收入信息，包括金额、商品名称/服务、商家、日期等。如果是账单或小票，请逐条列出每一项的金额和名称。",
                "image_source": data_url,
            })
            return result.content[0].text


def recognize_image(image_b64: str, mime_type: str) -> str | None:
    """同步包装：使用全局事件循环调用 MiniMax MCP。

    任何异常都被吞成 None 返回到上游，但必须把 traceback 留在日志里——
    否则 MCP 端口未启动 / 网络异常等部署问题会被静默掩盖。
    """
    try:
        future = asyncio.run_coroutine_threadsafe(
            _recognize_image_async(image_b64, mime_type), _loop
        )
        return future.result(timeout=30)
    except TimeoutError:
        logger.warning("图片识别超时（>30s），可能 MiniMax MCP 服务无响应")
        return None
    except Exception:
        logger.exception("图片识别失败（mime=%s）", mime_type)
        return None


# ── 工具调用处理（chat 和 chat_image 共用） ──────────────────────

def _process_tool_calls(tool_calls: list, llm_cfg: dict) -> tuple[list[str], list[dict], list[dict], list[dict]]:
    """处理 LLM 返回的工具调用。

    返回 (results, pending_records, pending_assets, pending_goals)。
    记账 / 投资资产 / 理财目标三类工具调用都被转成待确认卡片，
    避免 LLM 直接改库。
    """
    results = []
    pending_records = []
    pending_assets = []
    pending_goals = []
    for tc in tool_calls:
        func_name = tc["function"]["name"]
        params = json.loads(tc["function"]["arguments"])
        if func_name not in handlers:
            continue
        if func_name in ("add_record", "add_income"):
            rec_date = (params.get(PARAM_DATE) or "").strip() or datetime.now().strftime("%Y-%m-%d")
            rec = {
                "type": "expense" if func_name == "add_record" else "income",
                "category": params.get(PARAM_CATEGORY, ""),
                "amount": float(params.get(PARAM_AMOUNT, 0)),
                "date": rec_date,
                "note": params.get(PARAM_NOTE, ""),
            }
            pending_records.append(rec)
            rec_type = "支出" if func_name == "add_record" else "收入"
            results.append(
                f"已识别到{rec_type}：分类「{rec['category']}」金额 ¥{rec['amount']}，"
                f"备注「{rec['note']}」，日期 {rec['date']}，等待用户确认。"
            )
        elif func_name == "invest_add_asset":
            asset = {
                "name": (params.get("名称") or "").strip(),
                "type": (params.get("类型") or "other").strip(),
                "symbol": (params.get("代码") or "").strip(),
                "holdings": float(params.get("数量", 0) or 0),
                "cost_basis": float(params.get("成本", 0) or 0),
                "current_value": float(params.get("现值", 0) or 0),
                "notes": (params.get("备注") or "").strip(),
            }
            if not asset["name"]:
                continue
            pending_assets.append(asset)
            results.append(
                f"已识别到资产：「{asset['name']}」（{asset['type']}），"
                f"持仓 {asset['holdings']}，成本 ¥{asset['cost_basis']:.2f}，等待用户确认。"
            )
        elif func_name == "invest_add_goal":
            goal = {
                "name": (params.get("名称") or "").strip(),
                "target_amount": float(params.get("目标金额", 0) or 0),
                "deadline": (params.get("截止日期") or "").strip(),
                "current_progress": float(params.get("已完成", 0) or 0),
                "priority": int(params.get("优先级", 3) or 3),
                "note": (params.get("备注") or "").strip(),
            }
            if not goal["name"] or goal["target_amount"] <= 0:
                continue
            pending_goals.append(goal)
            results.append(
                f"已识别到理财目标：「{goal['name']}」目标 ¥{goal['target_amount']:.2f}，"
                f"优先级 {goal['priority']}，等待用户确认。"
            )
        elif func_name in ("suggest_budgets", "invest_analyze_portfolio"):
            r = handlers[func_name](g.user_id, params, llm_cfg)
            results.append(r)
        else:
            r = handlers[func_name](g.user_id, params)
            results.append(r)
    return results, pending_records, pending_assets, pending_goals


@chat_bp.route("/api/chat", methods=["POST"])
@login_required
def chat():
    data = request.get_json()
    llm_cfg = data.get("llm") or {}
    from services.llm_config import get_llm_config
    for k, v in (get_llm_config(g.user_id) or {}).items():
        llm_cfg.setdefault(k, v)

    user_msg = data.get("message", "")
    latest_msg = user_msg.strip().split("\n")[-1] if isinstance(user_msg, str) else user_msg

    add_chat_message(g.user_id, "user", user_msg)
    chat_history = get_chat_history(g.user_id)

    from services.profile import context_message
    profile_ctx = context_message(g.user_id)

    response = call_llm_intent(latest_msg, llm_cfg, FINANCE_TOOLS, extra_system=profile_ctx)

    reply = None
    pending_records = []
    pending_assets = []
    pending_goals = []
    tool_calls = None
    if response and "choices" in response:
        msg_obj = response["choices"][0].get("message", {})
        tool_calls = msg_obj.get("tool_calls")

        if tool_calls:
            results, pending_records, pending_assets, pending_goals = _process_tool_calls(tool_calls, llm_cfg)
            if results:
                llm_logger.info("Tools: %s", [tc['function']['name'] for tc in tool_calls])
                reply = call_llm_summary(latest_msg, "\n".join(results), llm_cfg)
        else:
            reply = msg_obj.get("content")

    if not reply:
        reply = call_llm_chat(chat_history, llm_cfg, extra_system=profile_ctx)

    add_chat_message(g.user_id, "assistant", reply)
    return jsonify({
        "reply": reply,
        "pending_records": pending_records,
        "pending_assets": pending_assets,
        "pending_goals": pending_goals,
    })


@chat_bp.route("/api/chat/image", methods=["POST"])
@login_required
def chat_image():
    """接收图片，调用 MiniMax 识别后走记账流程"""
    if "image" not in request.files:
        return jsonify({"success": False, "message": "未收到图片文件"}), 400

    file = request.files["image"]
    mime_type = file.content_type
    if mime_type not in ALLOWED_IMAGE_TYPES:
        return jsonify({"success": False, "message": f"不支持的图片格式：{mime_type}，仅支持 JPEG/PNG/WebP"}), 400

    image_bytes = file.read()
    if len(image_bytes) > MAX_IMAGE_SIZE:
        return jsonify({"success": False, "message": "图片大小超过 10MB 限制"}), 400

    # 1. 落盘归档：哪怕后续 OCR 失败，账单图本身也已保留供用户回查
    receipt_id = None
    try:
        from services.receipts import store_receipt
        receipt = store_receipt(g.user_id, image_bytes, mime_type)
        receipt_id = receipt["id"]
    except Exception as e:  # noqa: BLE001
        logger.warning("收据归档失败（不阻断识别流程）：%s", e)

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    del image_bytes

    recognized_text = recognize_image(image_b64, mime_type)
    del image_b64

    if not recognized_text:
        return jsonify({
            "reply": "图片识别失败，请重试或手动输入记账信息。",
            "pending_records": [],
            "receipt_id": receipt_id,  # 即便识别失败也可以让前端关联到手填记账
        })

    from services.llm_config import get_llm_config
    llm_cfg = get_llm_config(g.user_id) or {}

    user_msg = f"[图片识别结果] {recognized_text}"
    add_chat_message(g.user_id, "user", "[用户上传了一张图片]")

    response = call_llm_intent(user_msg, llm_cfg, FINANCE_TOOLS)

    reply = None
    pending_records = []
    pending_assets = []
    pending_goals = []
    tool_calls = None
    if response and "choices" in response:
        msg_obj = response["choices"][0].get("message", {})
        tool_calls = msg_obj.get("tool_calls")

        if tool_calls:
            results, pending_records, pending_assets, pending_goals = _process_tool_calls(tool_calls, llm_cfg)
            if results:
                llm_logger.info("[图片识别] Tools: %s", [tc['function']['name'] for tc in tool_calls])
                reply = call_llm_summary(user_msg, "\n".join(results), llm_cfg)
        else:
            reply = msg_obj.get("content")

    if not reply:
        chat_history = get_chat_history(g.user_id)
        reply = call_llm_chat(chat_history, llm_cfg)

    add_chat_message(g.user_id, "assistant", reply)
    # receipt_id 透传给前端，下一步 commit_record 时带上即可把图片关联到记录
    if receipt_id and pending_records:
        for rec in pending_records:
            rec["receipt_id"] = receipt_id
    return jsonify({
        "reply": reply,
        "pending_records": pending_records,
        "pending_assets": pending_assets,
        "pending_goals": pending_goals,
        "receipt_id": receipt_id,
    })


@chat_bp.route("/api/chat/history", methods=["GET"])
@login_required
def chat_history_api():
    """获取用户聊天记录"""
    history = get_chat_history(g.user_id)
    return jsonify(history)


@chat_bp.route("/api/profile", methods=["GET"])
@login_required
def get_user_profile():
    from services.profile import get_profile
    return jsonify(get_profile(g.user_id) or {"facts": None})


@chat_bp.route("/api/profile/refresh", methods=["POST"])
@login_required
def refresh_user_profile():
    from services.profile import refresh_profile
    from services.llm_config import get_llm_config
    llm_cfg = get_llm_config(g.user_id) or {}
    return jsonify(refresh_profile(g.user_id, llm=llm_cfg))


@chat_bp.route("/api/commit_record", methods=["POST"])
@login_required
def commit_record():
    data = request.get_json()
    rec_type = data.get("type")
    params = {
        PARAM_CATEGORY: data.get("category", "").strip(),
        PARAM_AMOUNT: float(data.get("amount", 0)),
        PARAM_NOTE: data.get("note", "").strip(),
        PARAM_DATE: data.get("date", "").strip(),
    }
    if not params[PARAM_CATEGORY] or not params[PARAM_AMOUNT]:
        return jsonify({"success": False, "message": "分类和金额不能为空"}), 400
    if rec_type == "expense":
        result = handlers["add_record"](g.user_id, params)
    elif rec_type == "income":
        result = handlers["add_income"](g.user_id, params)
    else:
        return jsonify({"success": False, "message": "未知类型"}), 400
    success = result.startswith("✅")

    # 如果用户从图片识别走过来并带了 receipt_id，把刚插入的记录与图片关联
    receipt_id = data.get("receipt_id")
    if success and receipt_id:
        try:
            from services.receipts import attach_to_record
            tbl = "records" if rec_type == "expense" else "income"
            row = get_db().execute(
                f"SELECT id FROM {tbl} WHERE user_id = ? AND category = ? AND amount = ? "
                f"AND date = ? ORDER BY id DESC LIMIT 1",
                (g.user_id, params[PARAM_CATEGORY], params[PARAM_AMOUNT], params[PARAM_DATE]),
            ).fetchone()
            if row:
                attach_to_record(g.user_id, int(receipt_id),
                                 record_id=row["id"], kind=rec_type)
        except Exception as e:  # noqa: BLE001
            logger.warning("收据关联失败（不阻断记账成功）：%s", e)

    # 预算预警：支出类型且成功时查询该分类本月预算状态
    budget_warning = None
    if success and rec_type == "expense":
        month = (data.get("date") or "")[:7]
        category = data.get("category", "").strip()
        if month and category:
            db = get_db()
            budget_row = db.execute(
                "SELECT amount FROM budgets WHERE user_id = ? AND category = ? AND month = ?",
                (g.user_id, category, month),
            ).fetchone()
            if budget_row:
                budget_amt = float(budget_row["amount"])
                spent = float(db.execute(
                    "SELECT COALESCE(SUM(amount),0) FROM records "
                    "WHERE user_id = ? AND category = ? AND strftime('%Y-%m', date) = ?",
                    (g.user_id, category, month),
                ).fetchone()[0])
                remaining = budget_amt - spent
                pct = spent / budget_amt * 100 if budget_amt > 0 else 0
                if remaining < 0:
                    budget_warning = {
                        "level": "over", "category": category,
                        "budget": budget_amt, "spent": round(spent, 2),
                        "remaining": round(remaining, 2),
                    }
                elif pct >= 80:
                    budget_warning = {
                        "level": "warn", "category": category,
                        "budget": budget_amt, "spent": round(spent, 2),
                        "remaining": round(remaining, 2),
                    }

    return jsonify({"success": success, "message": result, "budget_warning": budget_warning})
