"""行情服务：股票走新浪 / 基金走天天基金，带 SQLite 缓存，失败静默降级。

设计原则：
  * 不阻塞主流程——任何网络/解析错误都只记 warning 并返回 None
  * 10 分钟 TTL 缓存，避免反复打外部接口
  * 只支持股票与场外基金，其它类型（cash/bond/crypto/realestate/other）仍由用户手填
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)

QUOTE_TTL_SECONDS = 600
HTTP_TIMEOUT = 5.0

_SINA_URL = "https://hq.sinajs.cn/list={codes}"
_SINA_HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0 (ai-finance quotes)",
}
_FUND_URL = "http://fundgz.1234567.com.cn/js/{code}.js"
_FUND_HEADERS = {"User-Agent": "Mozilla/5.0 (ai-finance quotes)"}


@dataclass
class QuoteResult:
    symbol: str
    price: float
    name: str | None = None
    currency: str = "CNY"
    stale: bool = False


# ---------- 代码规范化 ----------

_FUND_CODE_RE = re.compile(r"^\d{6}$")


def _normalize_stock_symbol(symbol: str) -> str | None:
    """把用户输入的股票代码转换成新浪接口要求的前缀形式。

    支持：
        sh600519 / sz000001 / bj430047           → 原样
        600519 / 000001                         → 按首位自动补 sh/sz
        hk00700                                 → 原样
        gb_aapl / us_aapl                       → 美股（按 gb_ 前缀）
    """
    s = (symbol or "").strip().lower()
    if not s:
        return None
    if s.startswith(("sh", "sz", "bj", "hk", "gb_", "us_")):
        if s.startswith("us_"):
            return "gb_" + s[3:]
        return s
    if s.isdigit() and len(s) == 6:
        # A 股：6/9 开头沪市，其余深市
        return ("sh" if s[0] in "69" else "sz") + s
    return None


# ---------- 外部数据源 ----------

def _fetch_stock_quote(symbol: str) -> QuoteResult | None:
    code = _normalize_stock_symbol(symbol)
    if not code:
        return None
    try:
        resp = requests.get(
            _SINA_URL.format(codes=code),
            headers=_SINA_HEADERS,
            timeout=HTTP_TIMEOUT,
        )
        resp.encoding = "gbk"  # 新浪返回 gbk
        text = resp.text
    except (requests.RequestException, OSError) as e:
        logger.warning("[quote] sina fetch failed symbol=%s err=%s", symbol, e)
        return None

    # 返回格式：var hq_str_sh600519="贵州茅台,...,1680.00,..."; (A 股)
    m = re.search(r'="([^"]*)"', text)
    if not m or not m.group(1):
        logger.warning("[quote] sina empty response symbol=%s", symbol)
        return None
    parts = m.group(1).split(",")
    if len(parts) < 4:
        return None
    name = parts[0] or None

    # A 股 parts[3] = 当前价；港股 parts[6]；美股 parts[1]
    price: float | None = None
    if code.startswith(("sh", "sz", "bj")):
        try:
            price = float(parts[3] or 0) or float(parts[1] or 0)
        except ValueError:
            price = None
    elif code.startswith("hk"):
        try:
            price = float(parts[6]) if len(parts) > 6 else float(parts[3])
        except ValueError:
            price = None
    elif code.startswith("gb_"):
        try:
            price = float(parts[1])
        except ValueError:
            price = None

    if not price or price <= 0:
        return None
    return QuoteResult(symbol=symbol, price=round(price, 4), name=name)


def _fetch_fund_quote(symbol: str) -> QuoteResult | None:
    s = (symbol or "").strip()
    if not _FUND_CODE_RE.match(s):
        return None
    try:
        resp = requests.get(
            _FUND_URL.format(code=s),
            headers=_FUND_HEADERS,
            timeout=HTTP_TIMEOUT,
        )
        text = resp.text
    except (requests.RequestException, OSError) as e:
        logger.warning("[quote] fund fetch failed symbol=%s err=%s", symbol, e)
        return None

    m = re.search(r"jsonpgz\((\{.*?\})\);?", text)
    if not m:
        return None
    payload = m.group(1)
    # 手动解析，避免额外依赖
    try:
        import json as _json
        data = _json.loads(payload)
    except ValueError:
        return None
    # 估值优先（gsz），官方净值次之（dwjz）
    price_str = data.get("gsz") or data.get("dwjz") or ""
    try:
        price = float(price_str)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    return QuoteResult(symbol=s, price=round(price, 4), name=data.get("name") or None)


def fetch_quote(symbol: str, asset_type: str) -> QuoteResult | None:
    """统一入口：按 asset_type 分发到 stock / fund 两套抓取逻辑。"""
    if not symbol:
        return None
    t = (asset_type or "").strip().lower()
    if t == "stock":
        return _fetch_stock_quote(symbol)
    if t == "fund":
        return _fetch_fund_quote(symbol)
    return None


# ---------- 缓存 + 批量刷新 ----------

_AUTO_REFRESH_TYPES = ("stock", "fund")


def _get_cached(db, symbol: str, max_age: int) -> QuoteResult | None:
    row = db.execute(
        "SELECT symbol, asset_type, price, name, currency, fetched_at FROM quote_cache WHERE symbol = ?",
        (symbol,),
    ).fetchone()
    if not row:
        return None
    age = int(time.time()) - int(row["fetched_at"])
    if age > max_age:
        return None
    return QuoteResult(
        symbol=row["symbol"],
        price=float(row["price"]),
        name=row["name"],
        currency=row["currency"] or "CNY",
    )


def _put_cache(db, q: QuoteResult, asset_type: str) -> None:
    db.execute(
        """
        INSERT INTO quote_cache (symbol, asset_type, price, name, currency, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            asset_type = excluded.asset_type,
            price = excluded.price,
            name = excluded.name,
            currency = excluded.currency,
            fetched_at = excluded.fetched_at
        """,
        (q.symbol, asset_type, q.price, q.name, q.currency, int(time.time())),
    )


def get_quote(db, symbol: str, asset_type: str, *, force: bool = False) -> QuoteResult | None:
    """读缓存 → 命中直接返回；未命中或 force=True 则拉取外部行情并写回。"""
    if not symbol or asset_type not in _AUTO_REFRESH_TYPES:
        return None
    if not force:
        cached = _get_cached(db, symbol, QUOTE_TTL_SECONDS)
        if cached is not None:
            return cached
    fresh = fetch_quote(symbol, asset_type)
    if fresh is None:
        # 外部失败但缓存存在（即便过期）也返回旧值，标记 stale
        cached = _get_cached(db, symbol, max_age=10**9)
        if cached is not None:
            cached.stale = True
            return cached
        return None
    _put_cache(db, fresh, asset_type)
    db.commit()
    return fresh


def refresh_user_assets(db, user_id: int, *, force: bool = False) -> dict:
    """遍历该用户 shape=security_auto 的资产，按 quote_source 刷新 current_value。

    返回 {"updated": N, "skipped": M, "stale": K, "last_refreshed_at": iso}
    """
    rows = db.execute(
        "SELECT a.id, a.symbol, a.holdings, t.quote_source "
        "FROM assets a "
        "JOIN asset_types t ON t.user_id = a.user_id AND t.name = a.type "
        "WHERE a.user_id = ? AND t.shape = 'security_auto' "
        "AND t.quote_source IS NOT NULL",
        (user_id,),
    ).fetchall()

    updated = 0
    stale = 0
    skipped = 0
    now = int(time.time())

    for r in rows:
        asset_id = r["id"]
        quote_source = r["quote_source"]
        symbol = (r["symbol"] or "").strip()
        holdings = float(r["holdings"] or 0)
        if not symbol or holdings <= 0:
            skipped += 1
            continue
        q = get_quote(db, symbol, quote_source, force=force)
        if q is None:
            skipped += 1
            continue
        if q.stale:
            stale += 1
        new_value = round(q.price * holdings, 2)
        db.execute(
            "UPDATE assets SET current_value = ?, updated_at = ? WHERE id = ?",
            (new_value, _iso_now(), asset_id),
        )
        updated += 1

    db.commit()
    return {
        "updated": updated,
        "skipped": skipped,
        "stale": stale,
        "last_refreshed_at": _iso_from_epoch(now),
    }


def _iso_now() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def _iso_from_epoch(ts: int) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")
