#!/usr/bin/env python3
"""
AI Finance MCP Client
---------------------
用法一（命令行，供 Agent 子进程调用）:
    python finance_client.py <command> [options]

用法二（Python import，供 Python Agent 直接调用）:
    from finance_client import call_tool
    result = call_tool("add_record", {"category": "餐饮", "amount": 25.0})

环境变量:
    FINANCE_MCP_URL  MCP SSE 端点（默认 http://localhost:5001/mcp/sse）
    MCP_API_KEY      Bearer Token（与服务端 .env 中的 MCP_API_KEY 保持一致）
"""

import argparse
import asyncio
import json
import os
import sys

MCP_URL = os.getenv("FINANCE_MCP_URL", "http://localhost:5001/mcp/sse")
MCP_API_KEY = os.getenv("MCP_API_KEY", "changeme")


# ---------------------------------------------------------------------------
# 核心调用层
# ---------------------------------------------------------------------------

async def _call_tool_async(tool_name: str, args: dict) -> str:
    from mcp.client.sse import sse_client
    from mcp import ClientSession

    headers = {"Authorization": f"Bearer {MCP_API_KEY}"}
    async with sse_client(MCP_URL, headers=headers) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, args)
            return result.content[0].text


def call_tool(tool_name: str, args: dict = None) -> str:
    """通用工具调用接口，供 Python Agent import 后使用。"""
    return asyncio.run(_call_tool_async(tool_name, args or {}))


# ---------------------------------------------------------------------------
# 各工具封装（供 Python Agent import 后按语义调用）
# ---------------------------------------------------------------------------

def add_record(category: str, amount: float, note: str = "", date: str = "") -> str:
    """记录一笔支出。date 格式 YYYY-MM-DD，留空默认今天。"""
    return call_tool("add_record", {k: v for k, v in {
        "category": category, "amount": amount, "note": note, "date": date
    }.items() if v != ""})


def add_income(category: str, amount: float, note: str = "", date: str = "") -> str:
    """记录一笔收入。date 格式 YYYY-MM-DD，留空默认今天。"""
    return call_tool("add_income", {k: v for k, v in {
        "category": category, "amount": amount, "note": note, "date": date
    }.items() if v != ""})


def query_records(category: str = "", month: str = "", start_date: str = "",
                  end_date: str = "", limit: int = 20) -> str:
    """查询支出明细，所有参数可选。"""
    return call_tool("query_records", {k: v for k, v in {
        "category": category, "month": month,
        "start_date": start_date, "end_date": end_date, "limit": limit
    }.items() if v not in ("", 0)})


def query_income(source: str = "", month: str = "", show_all: bool = False) -> str:
    """查询收入记录，所有参数可选。"""
    args = {}
    if source:    args["source"] = source
    if month:     args["month"] = month
    if show_all:  args["show_all"] = True
    return call_tool("query_income", args)


def category_sum(category: str = "", month: str = "",
                 start_date: str = "", end_date: str = "") -> str:
    """统计支出总额，所有参数可选。"""
    return call_tool("category_sum", {k: v for k, v in {
        "category": category, "month": month,
        "start_date": start_date, "end_date": end_date
    }.items() if v})


def budget_remain(month: str = "", category: str = "") -> str:
    """查询预算剩余，留空返回当月全部分类。"""
    return call_tool("budget_remain", {k: v for k, v in {
        "month": month, "category": category
    }.items() if v})


def set_budget(category: str, amount: float, month: str = "") -> str:
    """设置或更新某分类的月预算。month 格式 YYYY-MM，留空默认当月。"""
    return call_tool("set_budget", {k: v for k, v in {
        "category": category, "amount": amount, "month": month
    }.items() if v not in ("", 0)})


def analyze_spend(month: str = "") -> str:
    """生成月度消费/收入排行分析报告，留空默认当月。"""
    return call_tool("analyze_spend", {"month": month} if month else {})


def list_categories() -> str:
    """获取所有支出和收入分类列表。"""
    return call_tool("list_categories", {})


# ---------------------------------------------------------------------------
# CLI 层（供 Agent 子进程调用）
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="finance_client.py",
        description="AI Finance MCP 客户端",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # add_record
    p = sub.add_parser("add_record", help="记录一笔支出")
    p.add_argument("--category", required=True, help="支出分类")
    p.add_argument("--amount",   required=True, type=float, help="金额")
    p.add_argument("--note",     default="", help="备注")
    p.add_argument("--date",     default="", help="日期 YYYY-MM-DD（默认今天）")

    # add_income
    p = sub.add_parser("add_income", help="记录一笔收入")
    p.add_argument("--category", required=True, help="收入来源")
    p.add_argument("--amount",   required=True, type=float, help="金额")
    p.add_argument("--note",     default="", help="备注")
    p.add_argument("--date",     default="", help="日期 YYYY-MM-DD（默认今天）")

    # query_records
    p = sub.add_parser("query_records", help="查询支出明细")
    p.add_argument("--category",   default="", help="按分类筛选")
    p.add_argument("--month",      default="", help="按月份筛选 YYYY-MM")
    p.add_argument("--start_date", default="", help="开始日期 YYYY-MM-DD")
    p.add_argument("--end_date",   default="", help="结束日期 YYYY-MM-DD")
    p.add_argument("--limit",      type=int, default=20, help="最多返回条数（默认20）")

    # query_income
    p = sub.add_parser("query_income", help="查询收入记录")
    p.add_argument("--source",   default="", help="按来源筛选")
    p.add_argument("--month",    default="", help="按月份筛选 YYYY-MM")
    p.add_argument("--show_all", action="store_true", help="返回全部明细列表")

    # category_sum
    p = sub.add_parser("category_sum", help="统计支出总额")
    p.add_argument("--category",   default="", help="按分类筛选")
    p.add_argument("--month",      default="", help="按月份筛选 YYYY-MM")
    p.add_argument("--start_date", default="", help="开始日期 YYYY-MM-DD")
    p.add_argument("--end_date",   default="", help="结束日期 YYYY-MM-DD")

    # budget_remain
    p = sub.add_parser("budget_remain", help="查询预算剩余")
    p.add_argument("--month",    default="", help="月份 YYYY-MM（默认当月）")
    p.add_argument("--category", default="", help="指定分类（留空返回全部）")

    # set_budget
    p = sub.add_parser("set_budget", help="设置或更新月预算")
    p.add_argument("--category", required=True, help="支出分类")
    p.add_argument("--amount",   required=True, type=float, help="预算金额")
    p.add_argument("--month",    default="", help="月份 YYYY-MM（默认当月）")

    # analyze_spend
    p = sub.add_parser("analyze_spend", help="月度消费分析报告")
    p.add_argument("--month", default="", help="月份 YYYY-MM（默认当月）")

    # list_categories
    sub.add_parser("list_categories", help="列出所有分类")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    cmd = args.command

    dispatch = {
        "add_record":      lambda: add_record(args.category, args.amount, args.note, args.date),
        "add_income":      lambda: add_income(args.category, args.amount, args.note, args.date),
        "query_records":   lambda: query_records(args.category, args.month, args.start_date, args.end_date, args.limit),
        "query_income":    lambda: query_income(args.source, args.month, args.show_all),
        "category_sum":    lambda: category_sum(args.category, args.month, args.start_date, args.end_date),
        "budget_remain":   lambda: budget_remain(args.month, args.category),
        "set_budget":      lambda: set_budget(args.category, args.amount, args.month),
        "analyze_spend":   lambda: analyze_spend(args.month),
        "list_categories": lambda: list_categories(),
    }

    try:
        print(dispatch[cmd]())
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
