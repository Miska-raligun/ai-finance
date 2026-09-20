"""静态行程页导入工具:JS 字面量解析与速查 HTML 转纯文本。

这两块是工具里唯一有判断逻辑的部分——正文里全是 "09:05"、"1/125" 这种
带冒号斜杠的字符串,解析一旦不区分字符串内外就会悄悄改坏内容。
"""
from __future__ import annotations

import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from jsliteral import load_literal, slice_literal  # noqa: E402
from import_trip import _text  # noqa: E402


def test_unquoted_keys_and_nested_arrays():
    src = 'const D=[{n:1,r:"上海 → 赫尔辛基",sched:[["05:05","集合","换护照",1]]}];'
    out = load_literal(src, "const D=")
    assert out[0]["n"] == 1
    assert out[0]["sched"][0] == ["05:05", "集合", "换护照", 1]


def test_colon_inside_string_is_not_treated_as_key():
    """时间 "09:05" 里的冒号不能让 09 变成键。"""
    out = load_literal('const D=[{t:"09:05 / 14:00",u:"1/125 秒"}];', "const D=")
    assert out[0]["t"] == "09:05 / 14:00"
    assert out[0]["u"] == "1/125 秒"


def test_brackets_inside_string_do_not_break_balancing():
    out = load_literal('const D=[{t:"这里有个 ] 和 }"},{t:"ok"}];', "const D=")
    assert [d["t"] for d in out] == ["这里有个 ] 和 }", "ok"]


def test_trailing_comma_and_single_quotes():
    out = load_literal("const P=[['a','b',],];", "const P=")
    assert out == [["a", "b"]]


def test_literals_true_false_null_survive():
    out = load_literal("const D=[{a:true,b:false,c:null}];", "const D=")
    assert out[0] == {"a": True, "b": False, "c": None}


def test_slice_stops_at_matching_bracket():
    src = "const D=[1,2];const PACK=[3];"
    assert slice_literal(src, "const D=") == "[1,2]"
    assert slice_literal(src, "const PACK=") == "[3]"


def test_text_br_becomes_newline():
    assert _text("芬兰 +358-9-0400618582<br>瑞典 +46-8-57936404") == \
        "芬兰 +358-9-0400618582\n瑞典 +46-8-57936404"


def test_text_table_rows_become_lines():
    html = "<table><tr><th>冰岛</th><td>8 小时</td></tr><tr><th>芬兰</th><td>6 小时</td></tr></table>"
    assert _text(html) == "冰岛　8 小时\n芬兰　6 小时"


def test_text_pills_get_separated():
    """并排的小标签去掉标签后不能粘成一长串。"""
    html = '<span class="pill">岩石教堂</span><span class="pill">蓝湖温泉</span>'
    assert _text(html) == "岩石教堂　蓝湖温泉"


def test_text_unescapes_entities_and_drops_blank_lines():
    assert _text("a &amp; b<br><br>c") == "a & b\nc"
