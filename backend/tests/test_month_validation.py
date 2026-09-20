"""month / period 参数的格式校验。

之前几个端点只判 `len(x) != 7`，"2026/04"、"2026-13" 这种正好 7 个字符的
非法值会被放行，一路带到 strftime 比较里静默查不到数据。
"""
import pytest

from validators import is_month


@pytest.mark.parametrize("value", ["2026-04", "1999-12", "2026-01"])
def test_valid_months(value):
    assert is_month(value)


@pytest.mark.parametrize("value", [
    "2026/04",   # 长度也是 7，只判长度会漏
    "2026-13",   # 月份越界
    "2026-00",
    "2026-4",
    "26-04",
    "2026-04-01",
    "",
    None,
    20260401,
])
def test_invalid_months(value):
    assert not is_month(value)


@pytest.mark.parametrize("path", [
    "/api/budgets/calibrate?month=2026/04",
    "/api/export/report.html?period=2026/04",
    "/api/reports/generate?month=2026/04",
    "/api/reports/2026/04/status",     # 会被路由成别的路径，一样不能 200
])
def test_endpoints_reject_bad_month(auth_client, path):
    r = auth_client.get(path) if not path.startswith("/api/reports/generate") \
        else auth_client.post(path)
    assert r.status_code != 200


def test_calibrate_apply_rejects_bad_month(auth_client):
    r = auth_client.post("/api/budgets/calibrate/apply",
                         json={"month": "2026-13", "items": [{"category": "餐饮",
                                                              "suggested_budget": 100}]})
    assert r.status_code == 400


def test_report_status_rejects_bad_month(auth_client):
    assert auth_client.get("/api/reports/2026-13/status").status_code == 400
    assert auth_client.get("/api/reports/2026-13").status_code == 400
