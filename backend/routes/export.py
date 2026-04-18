"""数据导出路由：CSV (records/income/assets) + 月报 HTML (可浏览器打印为 PDF)。"""
from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, abort, g, request

from auth import login_required
from db import get_db

export_bp = Blueprint("export", __name__)

# UTF-8 BOM 让 Excel 正确识别中文
_UTF8_BOM = "\ufeff"

_KIND_QUERIES = {
    "records": (
        "SELECT date, category, amount, note FROM records WHERE user_id = ? "
        "ORDER BY date DESC, id DESC",
        ["日期", "分类", "金额", "备注"],
    ),
    "income": (
        "SELECT date, category, amount, note FROM income WHERE user_id = ? "
        "ORDER BY date DESC, id DESC",
        ["日期", "来源", "金额", "备注"],
    ),
    "assets": (
        "SELECT name, type, symbol, holdings, cost_basis, current_value, currency, notes "
        "FROM assets WHERE user_id = ? ORDER BY current_value DESC",
        ["名称", "类型", "代码", "数量", "成本", "现值", "币种", "备注"],
    ),
}


@export_bp.route("/api/export/csv", methods=["GET"])
@login_required
def export_csv():
    kind = (request.args.get("type") or "records").strip()
    if kind not in _KIND_QUERIES:
        abort(400, description=f"不支持的导出类型：{kind}")

    sql, headers = _KIND_QUERIES[kind]
    rows = get_db().execute(sql, (g.user_id,)).fetchall()

    buf = io.StringIO()
    buf.write(_UTF8_BOM)
    writer = csv.writer(buf)
    writer.writerow(headers)
    for r in rows:
        writer.writerow([r[k] if r[k] is not None else "" for k in r.keys()])

    return Response(
        buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{kind}.csv"',
        },
    )


@export_bp.route("/api/export/report.html", methods=["GET"])
@login_required
def export_report_html():
    """把指定月份的报告渲染成可打印 HTML（用户在浏览器中 Cmd+P 转 PDF）。"""
    period = (request.args.get("period") or "").strip()
    if len(period) != 7:
        abort(400, description="period 参数应为 YYYY-MM")

    from services.reports import get_report
    rep = get_report(g.user_id, period)
    if not rep:
        abort(404, description="该月报告尚未生成")

    content = rep.get("content") or ""
    html = _render_report_html(period, rep.get("created_at") or "", content)
    return Response(html, mimetype="text/html; charset=utf-8")


def _render_report_html(period: str, created_at: str, markdown: str) -> str:
    """极简 Markdown→HTML 渲染（标题/列表/段落/强调），用于打印。"""
    import html as _html

    lines = markdown.split("\n")
    out: list[str] = []
    in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for line in lines:
        s = line.rstrip()
        if s.startswith("### "):
            close_list(); out.append(f"<h3>{_html.escape(s[4:])}</h3>"); continue
        if s.startswith("## "):
            close_list(); out.append(f"<h2>{_html.escape(s[3:])}</h2>"); continue
        if s.startswith("# "):
            close_list(); out.append(f"<h1>{_html.escape(s[2:])}</h1>"); continue
        if s.startswith("- ") or s.startswith("* "):
            if not in_list:
                out.append("<ul>"); in_list = True
            item = _html.escape(s[2:])
            item = _bold(item)
            out.append(f"<li>{item}</li>"); continue
        close_list()
        if not s.strip():
            out.append(""); continue
        out.append(f"<p>{_bold(_html.escape(s))}</p>")
    close_list()
    body = "\n".join(out)

    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>{period} 月度报告</title>
<style>
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         max-width: 760px; margin: 32px auto; padding: 0 24px; color: #1f2937; line-height: 1.7; }}
  h1 {{ font-size: 24px; border-bottom: 2px solid #3B82F6; padding-bottom: 6px; }}
  h2 {{ font-size: 18px; color: #2563EB; margin-top: 22px; }}
  h3 {{ font-size: 15px; margin-top: 16px; }}
  ul {{ padding-left: 22px; }}
  .meta {{ color: #6b7280; font-size: 12px; margin-bottom: 18px; }}
  @media print {{
    .no-print {{ display: none; }}
    body {{ margin: 0; padding: 0 12mm; }}
  }}
  .no-print {{ position: fixed; right: 16px; top: 16px;
              background: #3B82F6; color: #fff; border: none;
              padding: 8px 14px; border-radius: 6px; cursor: pointer; }}
</style></head>
<body>
  <button class="no-print" onclick="window.print()">🖨️ 打印 / 另存为 PDF</button>
  <h1>📑 {period} 月度报告</h1>
  <div class="meta">生成时间：{_html.escape(created_at)}</div>
  {body}
</body></html>"""


def _bold(s: str) -> str:
    import re as _re
    s = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = _re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s
