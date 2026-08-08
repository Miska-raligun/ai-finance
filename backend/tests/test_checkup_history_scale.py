"""asset_value_history 规模回归：5 资产 × 30 天快照 → 体检接口仍得正确 month_value_change。

把 _month_value_change 从相关子查询改成 window function 后，验证语义保持等价：
- 每 asset 取「月末/月前最后一条快照」加总；
- 已软删 asset 不计入；
- 没在期间内的 asset（首次出现在当月）也能正确累加。
"""
from datetime import datetime


def test_checkup_month_value_change_with_many_snapshots(auth_client, app, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    from db import get_db
    with auth_client.session_transaction() as s:
        uid = s["user_id"]

    period = datetime.now().strftime("%Y-%m")
    y, m = int(period[:4]), int(period[5:7])
    prev = f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"

    with app.app_context():
        db = get_db()
        # 5 个活资产 + 1 个软删资产
        for i in range(5):
            db.execute(
                "INSERT INTO assets (user_id, name, type, holdings, cost_basis, current_value) "
                "VALUES (?, ?, 'stock', 100, 500, 1000)",
                (uid, f"A{i}"),
            )
        db.execute(
            "INSERT INTO assets (user_id, name, type, holdings, cost_basis, current_value, deleted_at) "
            "VALUES (?, 'SOFT', 'stock', 50, 200, 999999, ?)",
            (uid, "2026-01-01T00:00:00"),
        )
        db.commit()
        asset_ids = [
            r["id"] for r in db.execute(
                "SELECT id FROM assets WHERE user_id = ? AND deleted_at IS NULL ORDER BY id",
                (uid,),
            ).fetchall()
        ]
        soft_id = db.execute(
            "SELECT id FROM assets WHERE user_id = ? AND name = 'SOFT'", (uid,)
        ).fetchone()["id"]

        # 每个活资产：前月最后一条 = 100*(i+1)，当月最后一条 = 100*(i+1) + 50
        # 月差 SUM = 5 * 50 = 250
        for i, aid in enumerate(asset_ids):
            db.execute(
                "INSERT INTO asset_value_history (user_id, asset_id, value, recorded_at) "
                "VALUES (?, ?, ?, ?)",
                (uid, aid, 100 * (i + 1), f"{prev}-15T09:00:00"),
            )
            db.execute(
                "INSERT INTO asset_value_history (user_id, asset_id, value, recorded_at) "
                "VALUES (?, ?, ?, ?)",
                (uid, aid, 100 * (i + 1) + 50, f"{period}-20T09:00:00"),
            )
        # 软删资产也写两条 history，应被 JOIN 过滤掉，不影响月差
        db.execute(
            "INSERT INTO asset_value_history (user_id, asset_id, value, recorded_at) "
            "VALUES (?, ?, 50000, ?)",
            (uid, soft_id, f"{prev}-15T09:00:00"),
        )
        db.execute(
            "INSERT INTO asset_value_history (user_id, asset_id, value, recorded_at) "
            "VALUES (?, ?, 999999, ?)",
            (uid, soft_id, f"{period}-20T09:00:00"),
        )
        # 给一笔记录以让 has_data=True，否则 compute 走 empty 分支
        db.execute(
            "INSERT INTO records (user_id, category, amount, note, date) "
            "VALUES (?, '餐饮', 50, '', ?)", (uid, f"{period}-05"))
        db.commit()

    body = auth_client.post(f"/api/checkup/compute?month={period}").get_json()
    portfolio = body["context"]["portfolio"]

    # 月差精确 = 5 * 50 = 250；软删资产的 +949999 不该混进来
    assert portfolio["month_value_change"] == 250.0
    # 累计市值（assets.current_value SUM，软删被 _aggregate_portfolio 排除）= 5 * 1000 = 5000
    assert portfolio["total_value"] == 5000.0
