"""从上传的文件里取出纯文本,喂给行程 AI。

旅行社发来的行程单基本就那么几种:Word、PDF、网页存下来的 HTML、
或者干脆是纯文本。让用户手动复制粘贴是没必要的麻烦。

依赖控制:docx / html / txt 全部用标准库解决(docx 就是个 zip,
里面 word/document.xml 是 XML);只有 PDF 绕不开,加了 pypdf(纯 Python,
无编译依赖)。扫描件那种图片 PDF 取不出文字,会明确告诉用户换一种方式。
"""
from __future__ import annotations

import io
import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

MAX_CHARS = 20000
SUPPORTED = (".docx", ".pdf", ".html", ".htm", ".txt", ".md")


class DocError(Exception):
    """取不出文字。message 直接给用户看。"""


# ---------- docx ----------

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _from_docx(data: bytes) -> str:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise DocError("这个 .docx 打不开,可能不是有效的 Word 文件")
    try:
        xml = zf.read("word/document.xml")
    except KeyError:
        raise DocError("这个 .docx 里没有正文,可能是旧版 .doc 改了后缀")

    root = ET.fromstring(xml)
    lines: list[str] = []
    # 一个 <w:p> 是一段,段内的文字散在若干 <w:t> 里;<w:tab> 当空格,
    # <w:br> 当换行。表格里的单元格同样是 <w:p>,所以顺带也能读出来。
    for para in root.iter(f"{_W}p"):
        buf: list[str] = []
        for node in para.iter():
            if node.tag == f"{_W}t":
                buf.append(node.text or "")
            elif node.tag == f"{_W}tab":
                buf.append("\t")
            elif node.tag == f"{_W}br":
                buf.append("\n")
        line = "".join(buf).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


# ---------- pdf ----------

def _from_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise DocError("服务端缺少 PDF 解析库,请把内容粘贴进来")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")           # 空密码的加密 PDF 很常见
            except Exception:  # noqa: BLE001
                raise DocError("这份 PDF 有密码,解不开")
        pages = [(p.extract_text() or "") for p in reader.pages[:60]]
    except DocError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning("PDF 解析失败: %s", e)
        raise DocError("这份 PDF 读不出来,换 Word 或者直接粘贴文字吧")

    text = "\n".join(pages).strip()
    if len(text) < 40:
        # 扫描件是一页页的图片,抽不出字符。与其给个空结果让 AI 瞎编,不如说清楚
        raise DocError("这份 PDF 里几乎没有文字,像是扫描件。"
                       "可以把文字复制出来粘贴,或者换 Word 版本")
    return text


# ---------- html ----------

class _Strip(HTMLParser):
    _SKIP = {"script", "style", "head", "noscript"}
    _BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "section"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
        elif tag in self._BLOCK:
            self.out.append("\n")
        elif tag in ("td", "th"):
            self.out.append("\t")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag in self._BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.out.append(data)


def _from_html(data: bytes) -> str:
    p = _Strip()
    p.feed(_decode(data))
    text = "".join(p.out)
    return re.sub(r"\n{3,}", "\n\n", text)


# ---------- 入口 ----------

def _decode(data: bytes) -> str:
    for enc in ("utf-8", "gb18030", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def extract_text(filename: str, data: bytes) -> str:
    name = (filename or "").lower().strip()
    if not data:
        raise DocError("文件是空的")
    if name.endswith(".doc"):
        raise DocError("旧版 .doc 读不了,用 Word 另存为 .docx 再传")
    if name.endswith(".docx"):
        text = _from_docx(data)
    elif name.endswith(".pdf"):
        text = _from_pdf(data)
    elif name.endswith((".html", ".htm")):
        text = _from_html(data)
    elif name.endswith((".txt", ".md")) or not name:
        text = _decode(data)
    else:
        raise DocError("支持 Word(.docx)、PDF、HTML 和纯文本;其它格式请粘贴内容")

    # 行程单里空行和制表符很多,压一压,省 token 也省得干扰模型
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 20:
        raise DocError("从文件里几乎没读出文字,换一种格式或者直接粘贴")
    return text[:MAX_CHARS]
