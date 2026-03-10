"""
AI Finance MCP Server - 为 Agent 提供直接调用记账工具的 MCP 接口
运行：python mcp_server.py
端口：5001 (MCP_PORT 可覆盖)
鉴权：Authorization: Bearer <username>:<password>
"""
import os, sys
from contextvars import ContextVar
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
from fastmcp import FastMCP
from db import get_db

_user_id: ContextVar[int] = ContextVar("user_id")
mcp = FastMCP("ai-finance", instructions="AI Finance 记账工具集。")


def uid() -> int:
    return _user_id.get()


@mcp.tool()
def add_record(category: str, amount: float, note: str = "", date: str = "") -> str:
    """记录一笔支出。category:分类, amount:金额, note:备注, date:YYYY-MM-DD(默认今天)"""
    if not date: date = datetime.now().strftime("%Y-%m-%d")
    month, year = date[:7], date[:4]
    db = get_db()
    row = db.execute("SELECT type FROM categories WHERE name=? AND user_id=?", (category, uid())).fetchone()
    if row and row["type"] == "收入": return f"⚠️ 「{category}」是收入来源，请更换分类名。"
    if not row: db.execute("INSERT INTO categories (user_id,name,type) VALUES (?,?,?)", (uid(), category, "支出"))
    db.execute("INSERT INTO records (user_id,category,amount,note,date,month,year) VALUES (?,?,?,?,?,?,?)", (uid(), category, amount, note, date, month, year))
    db.commit()
    return f"✅ 支出记录：{category} ¥{amount}，备注「{note}」，日期 {date}"

@mcp.tool()
def add_income(category: str, amount: float, note: str = "", date: str = "") -> str:
    """记录一笔收入。category:来源, amount:金额, note:备注, date:YYYY-MM-DD(默认今天)"""
    if not date: date = datetime.now().strftime("%Y-%m-%d")
    month, year = date[:7], date[:4]
    db = get_db()
    row = db.execute("SELECT type FROM categories WHERE name=? AND user_id=?", (category, uid())).fetchone()
    if row and row["type"] == "支出": return f"⚠️ 「{category}」已是支出分类，请更换名称。"
    if not row: db.execute("INSERT INTO categories (user_id,name,type) VALUES (?,?,?)", (uid(), category, "收入"))
    db.execute("INSERT INTO income (user_id,category,amount,note,date,month,year) VALUES (?,?,?,?,?,?,?)", (uid(), category, amount, note, date, month, year))
    db.commit()
    return f"✅ 收入记录：{category} ¥{amount}，备注「{note}」，日期 {date}"

@mcp.tool()
def category_sum(category: str = "", month: str = "", start_date: str = "", end_date: str = "") -> str:
    """统计支出总额。可按分类、月份(YYYY-MM)、日期范围筛选，均可选。"""
    db = get_db()
    q, args = "SELECT SUM(amount) FROM records WHERE user_id=?", [uid()]
    if category: q += " AND category=?"; args.append(category)
    if month: q += " AND month=?"; args.append(month)
    if start_date: q += " AND date>=?"; args.append(start_date)
    if end_date: q += " AND date<=?"; args.append(end_date)
    total = db.execute(q, args).fetchone()[0] or 0.0
    scope = month or (f"{start_date}~{end_date}" if start_date else "全部时间")
    return f"📊 {scope} {'「'+category+'」' if category else '全部'}支出合计：¥{total:.2f}"

@mcp.tool()
def query_records(category: str = "", month: str = "", start_date: str = "", end_date: str = "", limit: int = 20) -> str:
    """查询支出明细。可按分类、月份、日期范围筛选，limit默认20条。"""
    db = get_db()
    q, args = "SELECT date,category,amount,note FROM records WHERE user_id=?", [uid()]
    if category: q += " AND category=?"; args.append(category)
    if month: q += " AND month=?"; args.append(month)
    if start_date: q += " AND date>=?"; args.append(start_date)
    if end_date: q += " AND date<=?"; args.append(end_date)
    q += " ORDER BY date DESC LIMIT ?"; args.append(limit)
    rows = db.execute(q, args).fetchall()
    if not rows: return "暂无符合条件的支出记录。"
    return "\n".join(f"{r['date']} | {r['category']} | ¥{r['amount']} | {r['note']}" for r in rows)

@mcp.tool()
def query_income(source: str = "", month: str = "", show_all: bool = False) -> str:
    """查询收入。source:来源筛选, month:月份, show_all:True返回明细列表。"""
    db = get_db()
    if show_all:
        rows = db.execute("SELECT date,category,amount,note FROM income WHERE user_id=? ORDER BY date DESC LIMIT 20", (uid(),)).fetchall()
        total = db.execute("SELECT SUM(amount) FROM income WHERE user_id=?", (uid(),)).fetchone()[0] or 0
        return f"共{len(rows)}条收入，总计¥{total:.2f}：\n" + "\n".join(f"{r['date']}|{r['category']}|¥{r['amount']}|{r['note']}" for r in rows)
    q, args = "SELECT SUM(amount) FROM income WHERE user_id=?", [uid()]
    if source: q += " AND category=?"; args.append(source)
    if month: q += " AND month=?"; args.append(month)
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
        "SELECT category,SUM(amount) as total FROM records WHERE month=? AND user_id=? GROUP BY category", (month, uid())).fetchall()}
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
    spend = db.execute("SELECT category,SUM(amount) as t FROM records WHERE month=? AND user_id=? GROUP BY category ORDER BY t DESC LIMIT 5", (month, uid())).fetchall()
    income = db.execute("SELECT category,SUM(amount) as t FROM income WHERE month=? AND user_id=? GROUP BY category ORDER BY t DESC LIMIT 5", (month, uid())).fetchall()
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
    print(f"🚀 AI Finance MCP Server 启动，端口 {port}，用户凭据鉴权已启用")
    uvicorn.run(app, host="0.0.0.0", port=port)
