"""导出端点单测：CSV + 月报 HTML。"""
from __future__ import annotations


def test_export_records_csv(app, auth_client):
    from db import get_db
    from handlers import add_record
    from constants import PARAM_AMOUNT, PARAM_CATEGORY, PARAM_DATE, PARAM_NOTE

    with app.app_context():
        uid = get_db().execute("SELECT id FROM users WHERE username='tester'").fetchone()[0]
        add_record(uid, {PARAM_CATEGORY: "餐饮", PARAM_AMOUNT: 50,
                         PARAM_NOTE: "煎饼", PARAM_DATE: "2026-04-10"})

    r = auth_client.get("/api/export/csv?type=records")
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    body = r.data.decode("utf-8")
    assert body.startswith("\ufeff")  # UTF-8 BOM
    assert "日期" in body and "煎饼" in body and "餐饮" in body


def test_export_unsupported_type(auth_client):
    r = auth_client.get("/api/export/csv?type=hack")
    assert r.status_code == 400


def test_export_assets_csv_empty(auth_client):
    r = auth_client.get("/api/export/csv?type=assets")
    assert r.status_code == 200
    body = r.data.decode("utf-8")
    # 应只有 BOM + 表头
    assert "名称" in body and "现值" in body


def test_export_report_html_404(auth_client):
    r = auth_client.get("/api/export/report.html?period=2099-01")
    assert r.status_code == 404


def test_export_report_html_renders(app, auth_client, monkeypatch):
    from db import get_db
    from handlers import add_record
    from constants import PARAM_AMOUNT, PARAM_CATEGORY, PARAM_DATE
    from services.reports import generate_monthly_report

    monkeypatch.setattr(
        "services.llm.call_llm_monthly_report",
        lambda insights, llm=None: "# 月报\n## 概览\n- 总支出 100\n",
    )

    with app.app_context():
        uid = get_db().execute("SELECT id FROM users WHERE username='tester'").fetchone()[0]
        add_record(uid, {PARAM_CATEGORY: "餐饮", PARAM_AMOUNT: 100, PARAM_DATE: "2026-04-01"})
        generate_monthly_report(uid, period="2026-04")

    r = auth_client.get("/api/export/report.html?period=2026-04")
    assert r.status_code == 200
    assert r.mimetype == "text/html"
    body = r.data.decode("utf-8")
    assert "<h1>📑 2026-04" in body
    assert "<h2>概览</h2>" in body or "<h1>月报</h1>" in body
    assert "window.print()" in body
