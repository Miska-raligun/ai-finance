"""Sprint 3 智能特性单测：异常检测 / 分类缓存 / 月报聚合。"""
from __future__ import annotations

from datetime import date, timedelta


def _seed_lunch(uid: int, app):
    """插入 6 条 ¥30 午餐，用于异常基线。"""
    from handlers import add_record
    from constants import PARAM_AMOUNT, PARAM_CATEGORY, PARAM_DATE
    today = date.today()
    with app.app_context():
        for i in range(6):
            d = (today - timedelta(days=i + 1)).isoformat()
            add_record(uid, {PARAM_CATEGORY: "午餐", PARAM_AMOUNT: 30, PARAM_DATE: d})


def test_anomaly_flag_set_on_outlier(app, auth_client):
    from db import get_db
    from handlers import add_record
    from constants import PARAM_AMOUNT, PARAM_CATEGORY, PARAM_DATE

    with app.app_context():
        uid = get_db().execute("SELECT id FROM users WHERE username='tester'").fetchone()[0]

    _seed_lunch(uid, app)

    today = date.today().isoformat()
    with app.app_context():
        msg = add_record(uid, {PARAM_CATEGORY: "午餐", PARAM_AMOUNT: 300, PARAM_DATE: today})
        row = get_db().execute(
            "SELECT anomaly_flag, anomaly_score FROM records WHERE user_id = ? "
            "AND amount = 300 AND date = ?",
            (uid, today),
        ).fetchone()
    assert row["anomaly_flag"] == 1
    assert row["anomaly_score"] is not None and row["anomaly_score"] > 2.5
    assert "异常" in msg


def test_anomaly_skips_when_no_history(app, auth_client):
    from db import get_db
    from handlers import add_record
    from constants import PARAM_AMOUNT, PARAM_CATEGORY, PARAM_DATE

    with app.app_context():
        uid = get_db().execute("SELECT id FROM users WHERE username='tester'").fetchone()[0]
        today = date.today().isoformat()
        add_record(uid, {PARAM_CATEGORY: "午餐", PARAM_AMOUNT: 999, PARAM_DATE: today})
        row = get_db().execute(
            "SELECT anomaly_flag FROM records WHERE user_id = ?", (uid,)
        ).fetchone()
    assert row["anomaly_flag"] == 0


def test_categorizer_cache_hit(app, auth_client):
    """命中缓存时应直接返回 cache，不调用 LLM。"""
    from db import get_db
    from services.categorizer import remember, categorize

    with app.app_context():
        uid = get_db().execute("SELECT id FROM users WHERE username='tester'").fetchone()[0]
        get_db().execute(
            "INSERT INTO categories (user_id, name, type) VALUES (?, '咖啡', '支出')",
            (uid,),
        )
        get_db().commit()
        remember(uid, "星巴克拿铁", "咖啡")
        result = categorize(uid, "星巴克拿铁  ", llm={})
    assert result["source"] == "cache"
    assert result["category"] == "咖啡"


def test_categorizer_no_categories_returns_none(app, auth_client):
    from db import get_db
    from services.categorizer import categorize

    with app.app_context():
        uid = get_db().execute("SELECT id FROM users WHERE username='tester'").fetchone()[0]
        result = categorize(uid, "随便", llm={})
    assert result["source"] == "none"


def test_normalize_dedupes_punctuation(app):
    from services.categorizer import _normalize, _hash_note
    assert _normalize("星巴克 拿铁！！") == _normalize("星巴克拿铁")
    assert _hash_note(1, "Coffee.") == _hash_note(1, "coffee")


def test_reports_aggregate_no_data(app, auth_client):
    from db import get_db
    from services.reports import generate_monthly_report
    with app.app_context():
        uid = get_db().execute("SELECT id FROM users WHERE username='tester'").fetchone()[0]
        out = generate_monthly_report(uid, period="2099-01")
    assert out["stored"] is False
    assert "无任何记录" in out["content"]


def test_reports_aggregate_returns_totals(app, auth_client, monkeypatch):
    from db import get_db
    from handlers import add_record, add_income
    from constants import PARAM_AMOUNT, PARAM_CATEGORY, PARAM_DATE
    import services.reports as reports_mod

    monkeypatch.setattr(reports_mod, "__name__", reports_mod.__name__)

    with app.app_context():
        uid = get_db().execute("SELECT id FROM users WHERE username='tester'").fetchone()[0]
        add_record(uid, {PARAM_CATEGORY: "餐饮", PARAM_AMOUNT: 100, PARAM_DATE: "2026-04-01"})
        add_record(uid, {PARAM_CATEGORY: "餐饮", PARAM_AMOUNT: 50, PARAM_DATE: "2026-04-05"})
        add_income(uid, {PARAM_CATEGORY: "工资", PARAM_AMOUNT: 8000, PARAM_DATE: "2026-04-10"})

        # 桩掉 LLM 调用，避免外部依赖
        monkeypatch.setattr(
            "services.llm.call_llm_monthly_report",
            lambda insights, llm=None: f"# 报告 {insights['period']}\n",
        )
        out = reports_mod.generate_monthly_report(uid, period="2026-04")

    assert out["stored"] is True
    assert out["insights"]["spend_total"] == 150
    assert out["insights"]["income_total"] == 8000
    assert out["insights"]["net"] == 7850


def test_reports_routes_list_and_get(app, auth_client, monkeypatch):
    from db import get_db
    from handlers import add_record
    from constants import PARAM_AMOUNT, PARAM_CATEGORY, PARAM_DATE

    with app.app_context():
        uid = get_db().execute("SELECT id FROM users WHERE username='tester'").fetchone()[0]
        add_record(uid, {PARAM_CATEGORY: "餐饮", PARAM_AMOUNT: 100, PARAM_DATE: "2026-04-01"})

    monkeypatch.setattr(
        "services.reports.call_llm_monthly_report"
        if False else "services.llm.call_llm_monthly_report",
        lambda insights, llm=None: "# 月报\n内容",
    )

    r = auth_client.post("/api/reports/generate?month=2026-04")
    assert r.status_code == 200
    data = r.get_json()
    assert data["period"] == "2026-04"
    assert data["stored"] is True

    r2 = auth_client.get("/api/reports")
    assert r2.status_code == 200
    assert any(x["period"] == "2026-04" for x in r2.get_json())

    r3 = auth_client.get("/api/reports/2026-04")
    assert r3.status_code == 200
    assert r3.get_json()["content"].startswith("# 月报")

    r4 = auth_client.get("/api/reports/9999-01")
    assert r4.status_code == 404


def test_records_post_auto_categorize_uses_cache(app, auth_client):
    from db import get_db
    from services.categorizer import remember

    with app.app_context():
        uid = get_db().execute("SELECT id FROM users WHERE username='tester'").fetchone()[0]
        get_db().execute(
            "INSERT INTO categories (user_id, name, type) VALUES (?, '咖啡', '支出')",
            (uid,),
        )
        get_db().commit()
        remember(uid, "瑞幸生椰拿铁", "咖啡")

    r = auth_client.post("/api/records", json={
        "amount": 18, "note": "瑞幸生椰拿铁", "auto_categorize": True,
        "date": "2026-04-10",
    })
    body = r.get_json()
    assert r.status_code == 200, body
    assert body["success"] is True
    assert body["category"] == "咖啡"
    assert body["category_source"] == "cache"


def test_records_post_auto_categorize_needs_category(app, auth_client):
    """无缓存且无类目时返回 needs_category。"""
    r = auth_client.post("/api/records", json={
        "amount": 18, "note": "未知商家", "auto_categorize": True,
    })
    body = r.get_json()
    assert body["success"] is False
    assert body.get("needs_category") is True


def test_profile_save_and_context(app, auth_client):
    from db import get_db
    from services.profile import save_profile, context_message

    with app.app_context():
        uid = get_db().execute("SELECT id FROM users WHERE username='tester'").fetchone()[0]
        save_profile(uid, {
            "facts": {"income_band": "10k-20k", "preferences": ["咖啡"]},
            "income_band": "10k-20k",
        })
        ctx = context_message(uid)
    assert ctx is not None
    assert "10k-20k" in ctx
