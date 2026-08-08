"""只读 SQL 沙箱:让 MCP Agent 用任意 SELECT 灵活查询自己的账本。

动机:固定参数的查询工具没法表达"盒马总共花了多少"这种聚合——Agent 只能
拉全量明细自己加。开放 SQL 表达力,但必须锁死三条边界:

1. 行级隔离  —— 所有数据经「按 user_id 过滤的临时视图」暴露,真实表不可直接读。
2. 表级隔离  —— users / llm_config / captcha_store 等敏感表根本没有对应视图。
3. 只读      —— 连接以 mode=ro 打开(文件层拒写),authorizer 再拒掉一切
                非 SELECT 动作,双保险。

外加 max_rows 截断与 VM 步数上限(防 CROSS JOIN 跑飞)。
"""
from __future__ import annotations

import re
import sqlite3

# 暴露给 Agent 的视图:视图名 -> (真实表, 暴露列, 是否有软删列)
# 列里刻意不含 user_id / deleted_at——对单个用户来说它们是噪音。
EXPOSED_VIEWS: dict[str, tuple[str, str, bool]] = {
    "my_records": ("records", "id, date, category, amount, note, anomaly_flag", True),
    "my_income": ("income", "id, date, category, amount, note", True),
    "my_budgets": ("budgets", "id, category, amount, month", False),
    "my_categories": ("categories", "id, name, type", False),
    "my_assets": ("assets",
                  "id, name, type, symbol, holdings, cost_basis, current_value, "
                  "currency, notes, created_at, updated_at", True),
    "my_goals": ("financial_goals",
                 "id, name, target_amount, current_progress, deadline, priority, note", True),
    "my_asset_transactions": ("asset_transactions",
                              "id, asset_id, kind, quantity, price, fee, date, note", False),
    "my_recurring_rules": ("recurring_rules",
                           "id, kind, category, amount, day_of_month, note, active, "
                           "last_run_date", False),
    "my_asset_value_history": ("asset_value_history", "id, asset_id, value, recorded_at", False),
}

# 查询里允许的 authorizer 动作;其余(INSERT/UPDATE/DELETE/DDL/PRAGMA/ATTACH...)
# 一律 DENY。SQLITE_RECURSIVE 供 WITH RECURSIVE,SQLITE_FUNCTION 供 SUM/strftime 等。
_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
}

_MAX_VM_TICKS = 200          # progress_handler 每 100k 条 VM 指令回调一次
_PROGRESS_GRANULARITY = 100_000


class SandboxError(Exception):
    """查询被沙箱拒绝或执行失败,message 面向 Agent 可读。"""


def _make_authorizer():
    def _authorize(action, arg1, arg2, dbname, source):
        if action in _ALLOWED_ACTIONS:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            # 两条合法路径:直接读 temp 库里的白名单视图;
            # 或视图展开时经由白名单视图去读底层真实表(source=视图名)。
            if dbname == "temp" and arg1 in EXPOSED_VIEWS:
                return sqlite3.SQLITE_OK
            if source in EXPOSED_VIEWS:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_DENY
    return _authorize


def run_readonly_query(
    user_id: int, sql: str, *, db_file: str | None = None, max_rows: int = 200,
) -> tuple[list[str], list[tuple], bool]:
    """在沙箱里执行一条 SELECT,返回 (列名, 行, 是否被截断)。

    任何越权 / 语法错误 / 超时都抛 SandboxError,message 直接可展示给 Agent。
    """
    if db_file is None:
        import db as _db
        db_file = _db.DB_FILE

    stmt = (sql or "").strip().rstrip(";").strip()
    if not stmt:
        raise SandboxError("SQL 不能为空。")
    if ";" in stmt:
        raise SandboxError("一次只能执行一条语句。")
    if not re.match(r"^(select|with)\b", stmt, re.IGNORECASE):
        raise SandboxError("只允许 SELECT 查询(可用 WITH ... SELECT)。")

    uid = int(user_id)  # int 强转:视图 SQL 内联该值,杜绝注入
    conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    try:
        for view, (table, cols, soft_delete) in EXPOSED_VIEWS.items():
            alive = " AND deleted_at IS NULL" if soft_delete else ""
            try:
                conn.execute(
                    f"CREATE TEMP VIEW {view} AS "
                    f"SELECT {cols} FROM {table} WHERE user_id = {uid}{alive}"
                )
            except sqlite3.OperationalError:
                # 老库缺表(迁移没跑全)——跳过该视图,查询到它时会报"no such table"
                pass

        # 视图建完后再上 authorizer(建视图本身也是被 DENY 的动作)
        conn.set_authorizer(_make_authorizer())

        ticks = 0
        def _tick():
            nonlocal ticks
            ticks += 1
            return 1 if ticks > _MAX_VM_TICKS else 0
        conn.set_progress_handler(_tick, _PROGRESS_GRANULARITY)

        try:
            cur = conn.execute(stmt)
            rows = cur.fetchmany(max_rows + 1)
        except sqlite3.DatabaseError as e:
            msg = str(e)
            if "not authorized" in msg or "prohibited" in msg:
                raise SandboxError(
                    "查询涉及未开放的表/操作。只能读 my_* 开头的视图:"
                    + ", ".join(EXPOSED_VIEWS)
                ) from e
            if "interrupted" in msg:
                raise SandboxError("查询超出计算量上限,请缩小范围(加 WHERE / LIMIT)。") from e
            raise SandboxError(f"SQL 错误:{msg}") from e

        columns = [d[0] for d in cur.description] if cur.description else []
        truncated = len(rows) > max_rows
        return columns, rows[:max_rows], truncated
    finally:
        conn.close()
