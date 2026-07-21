"""对话相关路由：文本聊天、图片识别、记录确认"""
import os
import json
import time
import uuid
import base64
import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from flask import Blueprint, current_app, request, jsonify, g
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


def _classify_ocr_error(e: BaseException, mcp_port: str) -> str:
    """把底层异常翻译成用户/管理员能看懂的原因。

    anyio 的 task group 常把真实异常包在 ExceptionGroup 里,先解包;
    httpx 的连接异常类名都带 Connect,用类名嗅探避免顶层 import httpx。
    """
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    name = type(e).__name__
    if isinstance(e, (ConnectionError, OSError)) or "Connect" in name:
        return (f"无法连接图片识别服务（localhost:{mcp_port}）。"
                "请检查 minimax-mcp 服务是否在运行。")
    return f"图片识别服务异常（{name}），请稍后重试或手动输入。"


def recognize_image(image_b64: str, mime_type: str) -> tuple[str | None, str | None]:
    """同步包装：使用全局事件循环调用 MiniMax MCP。

    返回 (识别文本, 错误原因)。失败时文本为 None、原因为用户可读的一句话,
    同时把 traceback 留在日志里——否则 MCP 端口未启动 / 网络异常等部署问题
    会被静默掩盖。
    """
    mcp_port = os.getenv("MINIMAX_MCP_PORT", "5002")
    try:
        future = asyncio.run_coroutine_threadsafe(
            _recognize_image_async(image_b64, mime_type), _loop
        )
        text = future.result(timeout=30)
        return (text, None) if text else (None, "识别服务返回了空结果，请重试。")
    except TimeoutError:
        logger.warning("图片识别超时（>30s），可能 MiniMax MCP 服务无响应")
        return None, "图片识别超时（>30 秒），服务可能繁忙，请稍后重试。"
    except Exception as e:  # noqa: BLE001
        logger.exception("图片识别失败（mime=%s, mcp=localhost:%s）", mime_type, mcp_port)
        return None, _classify_ocr_error(e, mcp_port)


def _quota_reply(response) -> str | None:
    """LLM 每日配额耗尽时给出明确的用户可读回复,而不是落到"暂时无法回复"。
    调用方在拿到 _call_llm 结果后先过一遍这里,命中就直接短路返回。"""
    if isinstance(response, dict) and (response.get("error") or {}).get("code") == "quota_exceeded":
        return ("⏳ 今日 AI 额度已用完,明天 0 点自动重置。"
                "你仍然可以在「账本管理」页手动记账,或明天再来找我聊。")
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
    from services.llm_config import current_llm
    llm_cfg = current_llm(data)

    user_msg = data.get("message", "")
    latest_msg = user_msg.strip().split("\n")[-1] if isinstance(user_msg, str) else user_msg

    add_chat_message(g.user_id, "user", user_msg)
    chat_history = get_chat_history(g.user_id)

    from services.profile import context_message
    profile_ctx = context_message(g.user_id)

    response = call_llm_intent(latest_msg, llm_cfg, FINANCE_TOOLS, extra_system=profile_ctx)

    quota_msg = _quota_reply(response)
    if quota_msg:
        add_chat_message(g.user_id, "assistant", quota_msg)
        return jsonify({"reply": quota_msg, "pending_records": [],
                        "pending_assets": [], "pending_goals": []})

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


# ── 图片识别异步任务 ────────────────────────────────────────────
# OCR + LLM 全链路可能 30-60s。以前同步扛在请求里,用户干等、还容易撞反代
# 超时;现在上传立即返回 task_id,识别在线程池里跑,前端轮询取结果。
# 任务存进程内 dict(waitress 单进程多线程,够用);进程重启丢任务,前端轮询
# 超时后提示重试即可。
_IMG_TASK_TTL = 600  # 完成的任务保留 10 分钟,给前端慢轮询留余量
_img_tasks: dict[str, dict] = {}
_img_tasks_lock = threading.Lock()
_img_executor = ThreadPoolExecutor(
    max_workers=int(os.getenv("IMAGE_WORKERS", "2")),
    thread_name_prefix="img-task",
)


def _img_task_set(task_id: str, payload: dict) -> None:
    with _img_tasks_lock:
        _img_tasks[task_id] = payload
        # 顺手清理过期任务,避免长期运行后 dict 无限膨胀
        cutoff = time.time() - _IMG_TASK_TTL
        for k in [k for k, v in _img_tasks.items() if v.get("created_at", 0) < cutoff]:
            _img_tasks.pop(k, None)


def _run_image_task(app, task_id: str, user_id: int, image_b64: str,
                    mime_type: str, llm_cfg: dict, receipt_id) -> None:
    """线程池 worker:OCR → 意图识别 → 待确认卡片 → 总结。"""
    base = {"user_id": user_id, "created_at": time.time(), "receipt_id": receipt_id}
    with app.app_context():
        g.user_id = user_id  # _process_tool_calls 里的 handler 依赖 g.user_id
        try:
            recognized_text, ocr_err = recognize_image(image_b64, mime_type)
            if not recognized_text:
                _img_task_set(task_id, {
                    **base, "status": "failed",
                    "error": ocr_err or "图片识别服务无响应，请重试或手动输入记账信息。",
                })
                return

            user_msg = f"[图片识别结果] {recognized_text}"
            add_chat_message(user_id, "user", "[用户上传了一张图片]")

            response = call_llm_intent(user_msg, llm_cfg, FINANCE_TOOLS)

            quota_msg = _quota_reply(response)
            if quota_msg:
                add_chat_message(user_id, "assistant", quota_msg)
                _img_task_set(task_id, {
                    **base, "status": "done", "reply": quota_msg,
                    "pending_records": [], "pending_assets": [], "pending_goals": [],
                })
                return

            reply = None
            pending_records, pending_assets, pending_goals = [], [], []
            if response and "choices" in response:
                msg_obj = response["choices"][0].get("message", {})
                tool_calls = msg_obj.get("tool_calls")
                if tool_calls:
                    results, pending_records, pending_assets, pending_goals = \
                        _process_tool_calls(tool_calls, llm_cfg)
                    if results:
                        llm_logger.info("[图片识别] Tools: %s",
                                        [tc['function']['name'] for tc in tool_calls])
                        reply = call_llm_summary(user_msg, "\n".join(results), llm_cfg)
                else:
                    reply = msg_obj.get("content")

            if not reply:
                reply = call_llm_chat(get_chat_history(user_id), llm_cfg)

            add_chat_message(user_id, "assistant", reply)
            if receipt_id and pending_records:
                for rec in pending_records:
                    rec["receipt_id"] = receipt_id
            _img_task_set(task_id, {
                **base, "status": "done", "reply": reply,
                "pending_records": pending_records,
                "pending_assets": pending_assets,
                "pending_goals": pending_goals,
            })
        except Exception:  # noqa: BLE001
            logger.exception("图片识别任务失败 task=%s user=%s", task_id, user_id)
            _img_task_set(task_id, {
                **base, "status": "failed",
                "error": "识别过程出错，请重试或手动输入。",
            })


@chat_bp.route("/api/chat/image", methods=["POST"])
@login_required
def chat_image():
    """接收图片：校验 + 归档后立即返回 task_id,识别在后台线程池跑。"""
    if "image" not in request.files:
        return jsonify({"success": False, "message": "未收到图片文件"}), 400

    file = request.files["image"]
    mime_type = file.content_type
    if mime_type not in ALLOWED_IMAGE_TYPES:
        return jsonify({"success": False, "message": f"不支持的图片格式：{mime_type}，仅支持 JPEG/PNG/WebP"}), 400

    image_bytes = file.read()
    if len(image_bytes) > MAX_IMAGE_SIZE:
        return jsonify({"success": False, "message": "图片大小超过 10MB 限制"}), 400

    # 落盘归档：哪怕后续 OCR 失败，账单图本身也已保留供用户回查
    receipt_id = None
    try:
        from services.receipts import store_receipt
        receipt = store_receipt(g.user_id, image_bytes, mime_type)
        receipt_id = receipt["id"]
    except Exception as e:  # noqa: BLE001
        logger.warning("收据归档失败（不阻断识别流程）：%s", e)

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    del image_bytes

    # llm 配置要在请求上下文里取好快照,worker 线程里没有 g
    from services.llm_config import get_llm_config
    llm_cfg = get_llm_config(g.user_id) or {}

    task_id = uuid.uuid4().hex
    _img_task_set(task_id, {
        "user_id": g.user_id, "created_at": time.time(),
        "status": "pending", "receipt_id": receipt_id,
    })
    _img_executor.submit(
        _run_image_task, current_app._get_current_object(),
        task_id, g.user_id, image_b64, mime_type, llm_cfg, receipt_id,
    )
    return jsonify({"task_id": task_id, "status": "pending", "receipt_id": receipt_id}), 202


@chat_bp.route("/api/chat/image/tasks/<task_id>", methods=["GET"])
@login_required
def chat_image_task_status(task_id: str):
    """图片识别任务轮询端点。done/failed 后任务保留 10 分钟供重复拉取。"""
    with _img_tasks_lock:
        task = _img_tasks.get(task_id)
    if not task or task.get("user_id") != g.user_id:
        return jsonify({"error": "任务不存在或已过期"}), 404
    out = {k: v for k, v in task.items() if k not in ("user_id", "created_at")}
    return jsonify(out)


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
