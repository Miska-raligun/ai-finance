"""把 JS 对象字面量转成 JSON —— 给 import_trip.py 解析静态行程页用。

不用 `json.loads` 直接吃,是因为手写的页面里键没有引号(`{n:1,r:"…"}`)。
也不能拿正则粗暴加引号:正文里全是 "09:05"、"1/125" 这种带冒号斜杠的字符串,
一旦不区分字符串内外就会改坏内容。所以这里做一次最小的扫描:
只在字符串外把「标识符 + 冒号」的标识符补上引号,并顺手去掉尾随逗号。
"""
from __future__ import annotations

import json

_IDENT_START = "_$"
_WS = " \t\r\n"


def js_to_json(src: str) -> str:
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]

        # 字符串:原样搬运,只把引号统一成双引号并转义内部的双引号 / 换行
        if c in "\"'":
            quote = c
            out.append('"')
            i += 1
            while i < n:
                ch = src[i]
                if ch == "\\":
                    out.append(src[i:i + 2])
                    i += 2
                    continue
                if ch == quote:
                    break
                if ch == '"':
                    out.append('\\"')
                elif ch == "\n":
                    out.append("\\n")
                else:
                    out.append(ch)
                i += 1
            out.append('"')
            i += 1
            continue

        # 标识符:后面跟冒号说明是键,补引号;否则原样(true / false / null)
        if c.isalpha() or c in _IDENT_START:
            j = i
            while j < n and (src[j].isalnum() or src[j] in _IDENT_START):
                j += 1
            word = src[i:j]
            k = j
            while k < n and src[k] in _WS:
                k += 1
            out.append(f'"{word}"' if k < n and src[k] == ":" else word)
            i = j
            continue

        # 闭合括号前把尾随逗号丢掉,JSON 不允许
        if c in "]}":
            while out and out[-1].strip() == "" and out[-1] != "":
                out.pop()
            if out and out[-1] == ",":
                out.pop()

        out.append(c)
        i += 1
    return "".join(out)


def slice_literal(src: str, marker: str) -> str:
    """从 `marker`(如 `const D=`)之后截出一个完整的 [] / {} 字面量。

    按括号配平找结尾,并跳过字符串里的括号。
    """
    start = src.index(marker) + len(marker)
    while start < len(src) and src[start] in _WS:
        start += 1
    if src[start] not in "[{":
        raise ValueError(f"{marker} 后面不是数组或对象")
    opens = {"[": "]", "{": "}"}
    depth = 0
    i = start
    while i < len(src):
        ch = src[i]
        if ch in "\"'":
            quote = ch
            i += 1
            while i < len(src):
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == quote:
                    break
                i += 1
        elif ch in opens:
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
        i += 1
    raise ValueError(f"{marker} 的字面量没有闭合")


def load_literal(src: str, marker: str):
    return json.loads(js_to_json(slice_literal(src, marker)))
