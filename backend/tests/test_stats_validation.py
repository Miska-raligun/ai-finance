"""stats 路由参数校验：恶意/越界输入应 400 而非崩。"""


def test_summary_rejects_invalid_month(auth_client):
    r = auth_client.get("/api/stats/summary?month=2025-13")
    assert r.status_code == 400
    body = r.get_json()
    assert body["code"] == 400


def test_summary_rejects_non_iso_month(auth_client):
    r = auth_client.get("/api/stats/summary?month=20251")
    assert r.status_code == 400


def test_daily_requires_month(auth_client):
    r = auth_client.get("/api/stats/daily")
    assert r.status_code == 400


def test_daily_rejects_garbage_month(auth_client):
    """旧实现里 int(month[:4]) 会对非数字字符串抛 ValueError → 500，应改成 400。"""
    r = auth_client.get("/api/stats/daily?month=abcd-ef")
    assert r.status_code == 400


def test_comparison_year_validation(auth_client):
    r = auth_client.get("/api/stats/comparison?year=99")
    assert r.status_code == 400


def test_comparison_accepts_valid_month(auth_client):
    r = auth_client.get("/api/stats/comparison?month=2025-04")
    assert r.status_code == 200


def test_summary_default_uses_current_month(auth_client):
    r = auth_client.get("/api/stats/summary")
    assert r.status_code == 200
    assert "month" in r.get_json()
