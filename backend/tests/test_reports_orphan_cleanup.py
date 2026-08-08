"""进程重启后 reports 表里的 pending/running 行被收尸为 failed，避免前端永久轮询。"""
from datetime import datetime


def test_cleanup_orphan_reports_marks_failed(auth_client, app):
    from db import get_db
    from services.reports import cleanup_orphan_reports
    with auth_client.session_transaction() as s:
        uid = s["user_id"]
    now = datetime.now().isoformat(timespec="seconds")

    with app.app_context():
        db = get_db()
        # 三条遗留状态 + 一条 done，cleanup 只该动前三条。
        for period, status in [("2026-01", "pending"), ("2026-02", "running"),
                               ("2026-03", "pending"), ("2026-04", "done")]:
            db.execute(
                "INSERT INTO reports (user_id, period, format, status, "
                "created_at, updated_at) VALUES (?, ?, 'markdown', ?, ?, ?)",
                (uid, period, status, now, now),
            )
        db.commit()

        n = cleanup_orphan_reports()
        assert n == 3

        rows = db.execute(
            "SELECT period, status, error_message FROM reports "
            "WHERE user_id = ? ORDER BY period",
            (uid,),
        ).fetchall()
        statuses = {r["period"]: r["status"] for r in rows}
        msgs = {r["period"]: r["error_message"] for r in rows}
        assert statuses == {
            "2026-01": "failed", "2026-02": "failed",
            "2026-03": "failed", "2026-04": "done",
        }
        # 被清理的三条有错误信息，done 那条不被改
        assert "重启" in (msgs["2026-01"] or "")
        assert msgs["2026-04"] is None


def test_cleanup_orphan_reports_no_op_when_clean(app):
    """没有 pending/running 时返回 0，不报错。"""
    from services.reports import cleanup_orphan_reports
    with app.app_context():
        assert cleanup_orphan_reports() == 0
