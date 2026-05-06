"""
AI Finance MCP Server - 为 Agent 提供直接调用记账工具的 MCP 接口
运行：python mcp_server.py
端口：5001 (MCP_PORT 可覆盖)
鉴权：Authorization: Bearer <username>:<password>
"""
import os, sys, logging
from contextvars import ContextVar
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
from fastmcp import FastMCP
from db import get_db, cleanup_empty_category
import handlers
from constants import PARAM_CATEGORY, PARAM_AMOUNT, PARAM_NOTE, PARAM_DATE

logger = logging.getLogger(__name__)

_user_id: ContextVar[int] = ContextVar("user_id")
mcp = FastMCP("ai-finance", instructions="AI Finance 记账工具集。")


def uid() -> int:
    return _user_id.get()


@mcp.tool()
def add_record(category: str, amount: float, note: str = "", date: str = "") -> str:
    """记录一笔支出。category:分类, amount:金额, note:备注, date:YYYY-MM-DD(默认今天)"""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    return handlers.add_record(uid(), {
        PARAM_CATEGORY: category, PARAM_AMOUNT: amount,
        PARAM_NOTE: note, PARAM_DATE: date,
    })

@mcp.tool()
def add_income(category: str, amount: float, note: str = "", date: str = "") -> str:
    """记录一笔收入。category:来源, amount:金额, note:备注, date:YYYY-MM-DD(默认今天)"""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    return handlers.add_income(uid(), {
        PARAM_CATEGORY: category, PARAM_AMOUNT: amount,
        PARAM_NOTE: note, PARAM_DATE: date,
    })

@mcp.tool()
def category_sum(category: str = "", month: str = "", start_date: str = "", end_date: str = "") -> str:
    """统计支出总额。可按分类、月份(YYYY-MM)、日期范围筛选，均可选。"""
    db = get_db()
    q, args = "SELECT SUM(amount) FROM records WHERE user_id=?", [uid()]
    if category: q += " AND category=?"; args.append(category)
    if month: q += " AND strftime('%Y-%m', date)=?"; args.append(month)
    if start_date: q += " AND date>=?"; args.append(start_date)
    if end_date: q += " AND date<=?"; args.append(end_date)
    total = db.execute(q, args).fetchone()[0] or 0.0
    scope = month or (f"{start_date}~{end_date}" if start_date else "全部时间")
    return f"📊 {scope} {'「'+category+'」' if category else '全部'}支出合计：¥{total:.2f}"

@mcp.tool()
def query_records(category: str = "", month: str = "", start_date: str = "", end_date: str = "", limit: int = 20) -> str:
    """查询支出明细。可按分类、月份、日期范围筛选，limit默认20条。"""
    db = get_db()
    q, args = "SELECT id, date, category, amount, note FROM records WHERE user_id=?", [uid()]
    if category: q += " AND category=?"; args.append(category)
    if month: q += " AND strftime('%Y-%m', date)=?"; args.append(month)
    if start_date: q += " AND date>=?"; args.append(start_date)
    if end_date: q += " AND date<=?"; args.append(end_date)
    q += " ORDER BY date DESC LIMIT ?"; args.append(limit)
    rows = db.execute(q, args).fetchall()
    if not rows: return "暂无符合条件的支出记录。"
    return "\n".join(f"ID:{r['id']} | {r['date']} | {r['category']} | ¥{r['amount']} | {r['note']}" for r in rows)

@mcp.tool()
def query_income(source: str = "", month: str = "", show_all: bool = False) -> str:
    """查询收入。source:来源筛选, month:月份, show_all:True返回明细列表。"""
    db = get_db()
    if show_all:
        rows = db.execute("SELECT id, date, category, amount, note FROM income WHERE user_id=? ORDER BY date DESC LIMIT 20", (uid(),)).fetchall()
        total = db.execute("SELECT SUM(amount) FROM income WHERE user_id=?", (uid(),)).fetchone()[0] or 0
        return f"共{len(rows)}条收入，总计¥{total:.2f}：\n" + "\n".join(f"ID:{r['id']}|{r['date']}|{r['category']}|¥{r['amount']}|{r['note']}" for r in rows)
    q, args = "SELECT SUM(amount) FROM income WHERE user_id=?", [uid()]
    if source: q += " AND category=?"; args.append(source)
    if month: q += " AND strftime('%Y-%m', date)=?"; args.append(month)
    total = db.execute(q, args).fetchone()[0] or 0.0
    return f"💰 {month+' ' if month else ''}{'来源「'+source+'」' if source else '总'}收入：¥{total:.2f}"

@mcp.tool()
def budget_remain(month: str = "", category: str = "") -> str:
    """查询预算剩余。month:YYYY-MM(默认当月), category:分类(留空返回全部)。"""
    if not month: month = datetime.now().strftime("%Y-%m")
    db = get_db()
    budget_map = {r["category"]: float(r["amount"]) for r in db.execute(
        "SELECT b.category,b.amount FROM budgets b JOIN categories c ON b.category=c.name AND c.user_id=b.user_id WHERE b.month=? AND b.user_id=? AND c.type='支出'",
        (month, uid())).fetchall()}
    spend_map = {r["category"]: float(r["total"]) for r in db.execute(
        "SELECT category,SUM(amount) as total FROM records WHERE strftime('%Y-%m', date)=? AND user_id=? GROUP BY category", (month, uid())).fetchall()}
    if category:
        if category not in budget_map: return f"❌ 分类「{category}」在{month}没有设置预算。"
        spent = spend_map.get(category, 0)
        return f"📊 {month}「{category}」预算¥{budget_map[category]}，已花¥{spent}，剩余¥{budget_map[category]-spent:.2f}"
    if not budget_map: return f"📊 {month}暂无预算设置。"
    return f"📊 {month}预算剩余：\n" + "\n".join(f"- {c}：¥{b}预算，已花¥{spend_map.get(c,0)}，剩余¥{b-spend_map.get(c,0):.2f}" for c,b in budget_map.items())

@mcp.tool()
def analyze_spend(month: str = "") -> str:
    """消费分析，返回指定月份支出/收入排行。month:YYYY-MM(默认当月)。"""
    if not month: month = datetime.now().strftime("%Y-%m")
    db = get_db()
    spend = db.execute("SELECT category,SUM(amount) as t FROM records WHERE strftime('%Y-%m', date)=? AND user_id=? GROUP BY category ORDER BY t DESC LIMIT 5", (month, uid())).fetchall()
    income = db.execute("SELECT category,SUM(amount) as t FROM income WHERE strftime('%Y-%m', date)=? AND user_id=? GROUP BY category ORDER BY t DESC LIMIT 5", (month, uid())).fetchall()
    r = f"📊 {month}财务分析：\n\n💸 支出排行：\n"
    r += "\n".join(f"  {x['category']}：¥{x['t']:.2f}" for x in spend) if spend else "  暂无支出"
    r += "\n\n💰 收入排行：\n"
    r += "\n".join(f"  {x['category']}：¥{x['t']:.2f}" for x in income) if income else "  暂无收入"
    return r

@mcp.tool()
def list_categories() -> str:
    """获取所有支出和收入分类列表。"""
    db = get_db()
    rows = db.execute("SELECT name,type FROM categories WHERE user_id=? ORDER BY type,name", (uid(),)).fetchall()
    if not rows: return "暂无分类。"
    spend = [r["name"] for r in rows if r["type"] == "支出"]
    inc = [r["name"] for r in rows if r["type"] == "收入"]
    return ("💸 支出分类：" + "、".join(spend) + "\n" if spend else "") + ("💰 收入分类：" + "、".join(inc) if inc else "")

@mcp.tool()
def delete_record(record_id: int) -> str:
    """删除一条支出记录。请先用 query_records 查询获取 ID，再传入删除。"""
    db = get_db()
    row = db.execute(
        "SELECT id, category, amount, date, note FROM records WHERE id=? AND user_id=?",
        (record_id, uid())
    ).fetchone()
    if not row:
        return f"❌ 未找到 ID:{record_id} 的支出记录。"
    category = row['category']
    db.execute("DELETE FROM records WHERE id=? AND user_id=?", (record_id, uid()))
    db.commit()
    cleanup_empty_category(uid(), category)
    return f"✅ 已删除支出 ID:{record_id}，{row['date']} 「{category}」¥{row['amount']}（备注：{row['note']}）"

@mcp.tool()
def delete_income(income_id: int) -> str:
    """删除一条收入记录。请先用 query_income(show_all=True) 查询获取 ID，再传入删除。"""
    db = get_db()
    row = db.execute(
        "SELECT id, category, amount, date, note FROM income WHERE id=? AND user_id=?",
        (income_id, uid())
    ).fetchone()
    if not row:
        return f"❌ 未找到 ID:{income_id} 的收入记录。"
    category = row['category']
    db.execute("DELETE FROM income WHERE id=? AND user_id=?", (income_id, uid()))
    db.commit()
    cleanup_empty_category(uid(), category)
    return f"✅ 已删除收入 ID:{income_id}，{row['date']} 「{category}」¥{row['amount']}（备注：{row['note']}）"

@mcp.tool()
def list_asset_types() -> str:
    """列出当前用户定义的资产类型（name + shape + quote_source）。"""
    db = get_db()
    rows = db.execute(
        "SELECT name, shape, quote_source FROM asset_types "
        "WHERE user_id=? ORDER BY id ASC",
        (uid(),),
    ).fetchall()
    if not rows:
        return "暂无资产类型，先用 add_asset_type 创建。"
    lines = ["📚 你的资产类型："]
    for r in rows:
        src = f" · 行情源={r['quote_source']}" if r["quote_source"] else ""
        lines.append(f"- {r['name']}（{r['shape']}{src}）")
    return "\n".join(lines)


@mcp.tool()
def add_asset_type(name: str, shape: str, quote_source: str = "") -> str:
    """创建一个资产类型。
    shape ∈ security_auto / security_manual / lump / cash；
    quote_source 仅 shape=security_auto 时需填 stock 或 fund。
    """
    valid_shapes = {"security_auto", "security_manual", "lump", "cash"}
    if shape not in valid_shapes:
        return f"⚠️ 非法形态：{shape}，支持 {'/'.join(sorted(valid_shapes))}"
    qs = (quote_source or "").strip() or None
    if shape == "security_auto":
        if qs not in ("stock", "fund"):
            return "⚠️ security_auto 必须指定 quote_source=stock 或 fund"
    else:
        qs = None
    db = get_db()
    try:
        db.execute(
            "INSERT INTO asset_types (user_id, name, shape, quote_source, created_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (uid(), name.strip(), shape, qs),
        )
        db.commit()
    except Exception as e:
        return f"⚠️ 创建失败：{e}"
    return f"✅ 已创建类型「{name}」（{shape}{'·'+qs if qs else ''}）"


@mcp.tool()
def delete_asset_type(name: str) -> str:
    """删除一个资产类型；仍被资产引用时会拒绝。"""
    db = get_db()
    in_use = db.execute(
        "SELECT COUNT(*) AS c FROM assets WHERE user_id=? AND type=?",
        (uid(), name),
    ).fetchone()["c"]
    if in_use > 0:
        return f"⚠️ 类型「{name}」仍被 {in_use} 项资产引用，请先改类型或删除这些资产"
    res = db.execute(
        "DELETE FROM asset_types WHERE user_id=? AND name=?",
        (uid(), name),
    )
    db.commit()
    if res.rowcount == 0:
        return f"❌ 类型「{name}」不存在"
    return f"✅ 已删除类型「{name}」"


@mcp.tool()
def add_asset(name: str, type: str, current_value: float = 0,
              cost_basis: float = 0, holdings: float = 0,
              symbol: str = "", notes: str = "") -> str:
    """登记一项投资资产。type 必须是该用户已在 asset_types 里创建的类型名；
    可先用 list_asset_types 查看。"""
    return handlers.invest_add_asset(uid(), {
        "名称": name, "类型": type, "代码": symbol,
        "数量": holdings, "成本": cost_basis, "现值": current_value,
        "备注": notes,
    })


@mcp.tool()
def update_asset_value(name: str, current_value: float) -> str:
    """更新某项资产的当前市值。"""
    return handlers.invest_update_value(uid(), {"名称": name, "现值": current_value})


@mcp.tool()
def add_goal(name: str, target_amount: float, deadline: str = "",
             current_progress: float = 0, priority: int = 3, note: str = "") -> str:
    """创建理财目标。deadline 为 YYYY-MM-DD，priority 1-5。"""
    return handlers.invest_add_goal(uid(), {
        "名称": name, "目标金额": target_amount, "截止日期": deadline,
        "已完成": current_progress, "优先级": priority, "备注": note,
    })


@mcp.tool()
def portfolio_summary() -> str:
    """查看投资组合总览（总市值、类型分布、累计回报率）。"""
    return handlers.invest_portfolio_summary(uid())


@mcp.tool()
def rebalance_suggest(force: bool = False) -> str:
    """请 LLM 根据当前持仓 + 风险等级生成目标配比，返回各类型的 drift。"""
    from services.rebalance import suggest_rebalance
    from services.portfolio import compute_allocation
    db = get_db()
    rows = db.execute(
        "SELECT name, type, symbol, holdings, cost_basis, current_value "
        "FROM assets WHERE user_id = ?",
        (uid(),),
    ).fetchall()
    if not rows:
        return "📉 暂无资产，无法生成再平衡建议。"
    assets = [dict(r) for r in rows]
    allocation = compute_allocation(assets)
    risk_row = db.execute(
        "SELECT level FROM risk_profiles WHERE user_id = ?", (uid(),),
    ).fetchone()
    risk_level = risk_row["level"] if risk_row else None
    types = [dict(r) for r in db.execute(
        "SELECT name, shape, quote_source FROM asset_types WHERE user_id=?",
        (uid(),),
    ).fetchall()]
    result = suggest_rebalance(db, uid(), allocation, risk_level, types, force=force)
    if not result.get("drift"):
        return result.get("rationale") or "⚠️ 未生成建议"
    lines = [f"⚖️ 再平衡建议（{'刚生成' if result.get('source') == 'llm' else '缓存'}）："]
    if result.get("rationale"):
        lines.append(f"💡 {result['rationale']}")
    for row in result["drift"]:
        sign = "+" if row["drift_pct"] > 0 else ""
        lines.append(
            f"- {row['type']}：当前 {row['current_pct']:.1f}% / 建议 {row['target_pct']:.1f}% "
            f"（漂移 {sign}{row['drift_pct']:.1f}% → {row['action']}）"
        )
    return "\n".join(lines)


@mcp.tool()
def query_assets(type: str = "", symbol: str = "", limit: int = 50) -> str:
    """查询资产明细。type:按用户已定义的类型名筛选,
    symbol:按代码模糊匹配, limit:最多返回条数(默认50)。
    返回每笔持仓的 ID/名称/代码/类型/持仓/成本/现值/盈亏金额+百分比。
    """
    db = get_db()
    q = ("SELECT id, name, type, symbol, holdings, cost_basis, current_value, "
         "currency, notes FROM assets WHERE user_id=?")
    args: list = [uid()]
    if type:
        q += " AND type=?"; args.append(type)
    if symbol:
        q += " AND symbol LIKE ?"; args.append(f"%{symbol}%")
    q += " ORDER BY current_value DESC LIMIT ?"; args.append(limit)
    rows = db.execute(q, args).fetchall()
    if not rows:
        return "暂无符合条件的资产记录。"

    total_value = sum(float(r["current_value"] or 0) for r in rows)
    total_cost = sum(float(r["cost_basis"] or 0) for r in rows)
    total_pnl = total_value - total_cost

    lines = [f"📁 共 {len(rows)} 项资产，总市值 ¥{total_value:.2f}，"
             f"总成本 ¥{total_cost:.2f}，累计盈亏 ¥{total_pnl:+.2f}："]
    for r in rows:
        cost = float(r["cost_basis"] or 0)
        value = float(r["current_value"] or 0)
        pnl = value - cost
        pct = (pnl / cost * 100) if cost > 0 else 0.0
        holding = r["holdings"] or 0
        unit = (cost / holding) if holding > 0 else 0
        sym = r["symbol"] or "—"
        lines.append(
            f"ID:{r['id']} | {r['name']}({sym}) | {r['type']} | "
            f"持仓 {holding} | 成本价 ¥{unit:.4f} | 成本 ¥{cost:.2f} | "
            f"现值 ¥{value:.2f} | 盈亏 ¥{pnl:+.2f} ({pct:+.2f}%)"
        )
    return "\n".join(lines)


@mcp.tool()
def query_goals(show_all: bool = True) -> str:
    """查询理财目标列表。show_all=True 返回全部字段，否则只返回概要。"""
    db = get_db()
    rows = db.execute(
        "SELECT id, name, target_amount, current_progress, deadline, priority, "
        "COALESCE(note, '') AS note FROM financial_goals WHERE user_id=? "
        "ORDER BY priority ASC, deadline ASC",
        (uid(),),
    ).fetchall()
    if not rows:
        return "暂无理财目标。"
    lines = [f"🎯 共 {len(rows)} 个目标："]
    for r in rows:
        target = float(r["target_amount"] or 0)
        done = float(r["current_progress"] or 0)
        pct = (done / target * 100) if target > 0 else 0.0
        gap = max(0.0, target - done)
        base = (f"ID:{r['id']} | {r['name']} | 目标 ¥{target:.2f} | "
                f"已完成 ¥{done:.2f} ({pct:.1f}%) | 缺口 ¥{gap:.2f} | "
                f"截止 {r['deadline'] or '未设'} | 优先级 {r['priority']}")
        if show_all and r["note"]:
            base += f" | 备注：{r['note']}"
        lines.append(base)
    return "\n".join(lines)


@mcp.tool()
def query_asset_transactions(asset_id: int = 0, limit: int = 20) -> str:
    """查询资产交易流水。asset_id=0 时返回所有资产的最近交易；指定则只看该资产。"""
    db = get_db()
    q = ("SELECT t.id, t.asset_id, a.name AS asset_name, t.kind, t.quantity, "
         "t.price, t.fee, t.date, COALESCE(t.note, '') AS note "
         "FROM asset_transactions t JOIN assets a ON t.asset_id=a.id "
         "WHERE t.user_id=?")
    args: list = [uid()]
    if asset_id > 0:
        q += " AND t.asset_id=?"; args.append(asset_id)
    q += " ORDER BY t.date DESC, t.id DESC LIMIT ?"; args.append(limit)
    rows = db.execute(q, args).fetchall()
    if not rows:
        return "暂无交易流水。"
    lines = [f"📜 最近 {len(rows)} 条交易："]
    for r in rows:
        qty = float(r["quantity"] or 0)
        price = float(r["price"] or 0)
        fee = float(r["fee"] or 0)
        amount = qty * price + fee
        lines.append(
            f"ID:{r['id']} | {r['date']} | {r['asset_name']}(资产#{r['asset_id']}) | "
            f"{r['kind']} | 数量 {qty} | 价 ¥{price:.4f} | 费 ¥{fee:.2f} | "
            f"合计 ¥{amount:.2f} | {r['note']}"
        )
    return "\n".join(lines)


@mcp.tool()
def refresh_portfolio_prices() -> str:
    """强制刷新股票/基金行情并更新 current_value（忽略 10 分钟缓存）。"""
    return handlers.invest_refresh_prices(uid())


@mcp.tool()
def quote_symbol(symbol: str, asset_type: str = "stock") -> str:
    """按代码查询一次最新行情（不持久化）。asset_type 只支持 stock / fund。"""
    from services.quotes import fetch_quote
    q = fetch_quote(symbol, asset_type)
    if q is None:
        return f"❌ 未能获取 {symbol} 的 {asset_type} 行情（代码格式不对或数据源异常）"
    name = q.name or symbol
    return f"📈 {name}（{symbol}）最新价：¥{q.price:.4f}"


@mcp.tool()
def update_asset(asset_id: int, name: str = "", current_value: float = -1,
                 holdings: float = -1, cost_basis: float = -1,
                 symbol: str = "", notes: str = "") -> str:
    """按 ID 更新资产字段。未提供的字段会被忽略（current_value/holdings/cost_basis 传 -1 表示不变）。"""
    db = get_db()
    row = db.execute(
        "SELECT id FROM assets WHERE id=? AND user_id=?", (asset_id, uid()),
    ).fetchone()
    if not row:
        return f"❌ 未找到 ID:{asset_id} 的资产"
    updates = {}
    if name: updates["name"] = name
    if current_value >= 0: updates["current_value"] = current_value
    if holdings >= 0: updates["holdings"] = holdings
    if cost_basis >= 0: updates["cost_basis"] = cost_basis
    if symbol: updates["symbol"] = symbol
    if notes: updates["notes"] = notes
    if not updates:
        return "⚠️ 未提供任何要更新的字段"
    sets = ", ".join(f"{k}=?" for k in updates) + ", updated_at=?"
    values = list(updates.values()) + [datetime.now().isoformat(timespec="seconds"), asset_id, uid()]
    try:
        db.execute(f"UPDATE assets SET {sets} WHERE id=? AND user_id=?", values)
        db.commit()
    except Exception as e:
        return f"⚠️ 更新失败：{e}"
    from cache import invalidate_user
    invalidate_user(uid())
    return f"✅ 已更新资产 ID:{asset_id}"


@mcp.tool()
def delete_asset(asset_id: int) -> str:
    """按 ID 删除一项资产（连带删除其交易流水）。"""
    db = get_db()
    row = db.execute(
        "SELECT name FROM assets WHERE id=? AND user_id=?", (asset_id, uid()),
    ).fetchone()
    if not row:
        return f"❌ 未找到 ID:{asset_id} 的资产"
    db.execute("DELETE FROM assets WHERE id=? AND user_id=?", (asset_id, uid()))
    db.execute("DELETE FROM asset_transactions WHERE asset_id=? AND user_id=?", (asset_id, uid()))
    db.commit()
    from cache import invalidate_user
    invalidate_user(uid())
    return f"✅ 已删除资产「{row['name']}」(ID:{asset_id})"


@mcp.tool()
def sell_asset(asset_id: int, price: float, quantity: float = 0,
               fee: float = 0, date: str = "", note: str = "") -> str:
    """卖出资产并自动把盈亏结算到收入或支出。

    quantity=0 表示全部卖出。盈利 → 收入分类「投资盈利」；亏损 → 支出分类
    「投资亏损」（自动建分类）。备注会自动拼接成本/出场金额/卖出价等。
    持仓清零则资产被删除；部分卖出则按比例减 holdings / cost_basis。
    可先用 query_assets 拿 ID。
    """
    from services.asset_settle import sell_asset as _sell, SettleError
    from cache import invalidate_user
    try:
        r = _sell(get_db(), uid(), asset_id,
                  price=price, quantity=quantity if quantity > 0 else None,
                  fee=fee, date=date or None, note=note)
    except SettleError as e:
        return f"⚠️ 卖出失败：{e}"
    invalidate_user(uid())
    pnl = r["pnl"]
    pnl_str = f"+¥{pnl:.2f}" if pnl > 0 else f"-¥{abs(pnl):.2f}" if pnl < 0 else "¥0.00"
    ledger = {"income": "已计入收入「投资盈利」", "expense": "已计入支出「投资亏损」",
              "none": "盈亏接近 0，未写入收支表"}.get(r["ledger"], "")
    suffix = "已删除资产" if r["remaining_holdings"] == 0 else f"剩余持仓 {r['remaining_holdings']}"
    return (f"✅ 已卖出「{r['asset_name']}」{r['sold_qty']} 份 @ ¥{r['price']:.4f}\n"
            f"   回款 ¥{r['proceeds']:.2f} / 摊销成本 ¥{r['cost']:.2f} / 盈亏 {pnl_str}\n"
            f"   {ledger}；{suffix}")


@mcp.tool()
def archive_asset(asset_id: int, date: str = "", note: str = "") -> str:
    """归档资产：按当前 current_value 一次性结算盈亏并删除资产。

    用于停止追踪某项资产、或现金类 / 一次性资产平账。盈亏写入收入/支出，
    备注会标注"按归档时市值 ¥X 结算"。可先用 query_assets 拿 ID。
    """
    from services.asset_settle import archive_asset as _archive, SettleError
    from cache import invalidate_user
    try:
        r = _archive(get_db(), uid(), asset_id, date=date or None, note=note)
    except SettleError as e:
        return f"⚠️ 归档失败：{e}"
    invalidate_user(uid())
    pnl = r["pnl"]
    pnl_str = f"+¥{pnl:.2f}" if pnl > 0 else f"-¥{abs(pnl):.2f}" if pnl < 0 else "¥0.00"
    ledger = {"income": "已计入收入「投资盈利」", "expense": "已计入支出「投资亏损」",
              "none": "盈亏接近 0，未写入收支表"}.get(r["ledger"], "")
    return (f"📦 已归档「{r['asset_name']}」（{r['asset_type']}）\n"
            f"   出场金额 ¥{r['proceeds']:.2f} / 成本 ¥{r['cost']:.2f} / 盈亏 {pnl_str}\n"
            f"   {ledger}")


@mcp.tool()
def set_budget(category: str, amount: float, month: str = "") -> str:
    """设置或更新某分类的月预算。month:YYYY-MM(默认当月)。"""
    if not month: month = datetime.now().strftime("%Y-%m")
    db = get_db()
    row = db.execute("SELECT type FROM categories WHERE name=? AND user_id=?", (category, uid())).fetchone()
    if row and row["type"] != "支出": return f"⚠️ 分类「{category}」不是支出分类。"
    if not row: db.execute("INSERT INTO categories (user_id,name,type) VALUES (?,?,?)", (uid(), category, "支出"))
    db.execute("INSERT OR REPLACE INTO budgets (user_id,category,amount,cycle,month) VALUES (?,?,?,?,?)", (uid(), category, amount, "月", month))
    db.commit()
    return f"✅ 已设置{month}「{category}」预算：¥{amount}"


if __name__ == "__main__":
    import uvicorn
    from werkzeug.security import check_password_hash
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    class UserAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            token = auth[len("Bearer "):]
            if ":" not in token:
                return JSONResponse({"error": "Invalid credentials format, expected username:password"}, status_code=401)
            username, password = token.split(":", 1)
            db = get_db()
            row = db.execute("SELECT id, password FROM users WHERE username=?", (username,)).fetchone()
            if not row or not check_password_hash(row["password"], password):
                return JSONResponse({"error": "Invalid username or password"}, status_code=401)
            token_var = _user_id.set(row["id"])
            try:
                return await call_next(request)
            finally:
                _user_id.reset(token_var)

    port = int(os.getenv("MCP_PORT", "5001"))
    app = mcp.http_app(path="/mcp")
    app.add_middleware(UserAuthMiddleware)
    logger.info("AI Finance MCP Server 启动，端口 %d，用户凭据鉴权已启用", port)
    uvicorn.run(app, host="0.0.0.0", port=port)
