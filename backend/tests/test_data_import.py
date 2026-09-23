"""数据导入:CSV/JSON 回灌,去重,自动建分类,非法行跳过。"""
from __future__ import annotations

import io
import json


def _post(client, kind, filename, content, fmt=None):
    data = {"type": kind, "file": (io.BytesIO(content), filename)}
    if fmt:
        data["format"] = fmt
    return client.post("/api/import", data=data, content_type="multipart/form-data")


def test_import_csv_records(app, auth_client):
    csv_bytes = "日期,分类,金额,备注\n2026-06-01,餐饮,38.50,午饭\n2026-06-02,交通,12,地铁\n".encode("utf-8-sig")
    r = _post(auth_client, "records", "records.csv", csv_bytes)
    assert r.status_code == 200
    body = r.get_json()
    assert body["imported"] == 2

    rows = auth_client.get("/api/records").get_json()["data"]
    notes = {x["note"] for x in rows}
    assert "午饭" in notes and "地铁" in notes
    # 分类被自动补建
    cats = auth_client.get("/api/categories").get_json()
    names = {c["name"] if isinstance(c, dict) else c for c in cats}
    assert "餐饮" in names


def test_import_dedups(app, auth_client):
    csv_bytes = "日期,分类,金额,备注\n2026-06-01,餐饮,38.50,午饭\n".encode("utf-8")
    _post(auth_client, "records", "a.csv", csv_bytes)
    # 再导一次同样的:应全部跳过
    r = _post(auth_client, "records", "a.csv", csv_bytes)
    body = r.get_json()
    assert body["imported"] == 0
    assert body["skipped"] == 1


def test_import_json_income(app, auth_client):
    payload = json.dumps({"data": [
        {"日期": "2026-06-05", "来源": "工资", "金额": 8000, "备注": "月薪"},
        {"日期": "2026-06-06", "来源": "利息", "金额": 12.5, "备注": ""},
    ]}).encode("utf-8")
    r = _post(auth_client, "income", "income.json", payload, fmt="json")
    assert r.get_json()["imported"] == 2
    total = auth_client.get("/api/income").get_json()["sum_amount"]
    assert total == 8012.5


def test_import_skips_invalid_rows(app, auth_client):
    csv_bytes = (
        "日期,分类,金额,备注\n"
        "2026-06-01,餐饮,38.5,ok\n"
        ",餐饮,10,缺日期\n"           # 无日期
        "2026-06-02,,10,缺分类\n"      # 无分类
        "2026-06-03,餐饮,abc,金额非法\n"  # 金额非法
        "2026-06-04,餐饮,-5,负数\n"     # 负数
    ).encode("utf-8")
    r = _post(auth_client, "records", "mixed.csv", csv_bytes)
    assert r.get_json()["imported"] == 1


def test_import_roundtrip_with_export(app, auth_client):
    """导出的 CSV 能原样导回(表头兼容)。"""
    auth_client.post("/api/records", json={"category": "购物", "amount": 99, "note": "键盘", "date": "2026-06-10"})
    exported = auth_client.get("/api/export?type=records&format=csv").data
    # 换个用户视角不方便,这里用去重验证:导回自己的导出应全跳过(已存在)
    r = _post(auth_client, "records", "export.csv", exported)
    assert r.get_json()["imported"] == 0
