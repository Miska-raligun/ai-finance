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

def _parse_sina_payload(code: str, payload: str) -> tuple[str | None, float | None]:
    """从 sina 返回的单条 csv-like payload 中解析 (name, price)。"""
    parts = payload.split(",")
    if len(parts) < 4:
        return None, None
    name = parts[0] or None
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
        return name, None
    return name, round(price, 4)


def _fetch_stock_quote(symbol: str) -> QuoteResult | None:
    """单条抓取：内部仅供 fetch_quote 使用，批量场景请走 _fetch_stock_quotes_batch。"""
    res = _fetch_stock_quotes_batch([symbol])
    return res.get(symbol)


def _fetch_stock_quotes_batch(symbols: list[str]) -> dict[str, QuoteResult]:
    """新浪行情接口支持以逗号拼接多个代码，单次请求即可拿全部价格。

    返回 {原始 symbol: QuoteResult}；解析失败/代码非法的 symbol 不会出现在结果中。
    """
    pairs: list[tuple[str, str]] = []  # (原始 symbol, sina code)
    for s in symbols:
        code = _normalize_stock_symbol(s)
        if code:
            pairs.append((s, code))
    if not pairs:
        return {}

    # 单次最多打包 50 个，避免 URL 过长
    out: dict[str, QuoteResult] = {}
    chunk = 50
    for i in range(0, len(pairs), chunk):
        batch = pairs[i:i + chunk]
        codes = ",".join(c for _, c in batch)
        try:
            resp = requests.get(
                _SINA_URL.format(codes=codes),
                headers=_SINA_HEADERS,
                timeout=HTTP_TIMEOUT,
            )
            resp.encoding = "gbk"
            text = resp.text
        except (requests.RequestException, OSError) as e:
            logger.warning("[quote] sina batch fetch failed n=%d err=%s", len(batch), e)
            continue

        # 每行形如：var hq_str_sh600519="贵州茅台,...";
        line_re = re.compile(r'hq_str_([^=]+)="([^"]*)"')
        payloads = {m.group(1).strip(): m.group(2) for m in line_re.finditer(text)}
        for orig, code in batch:
            payload = payloads.get(code)
            if not payload:
                continue
            name, price = _parse_sina_payload(code, payload)
            if price is None:
                continue
            out[orig] = QuoteResult(symbol=orig, price=price, name=name)
    return out


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

    优化点：
      * 股票走批量接口（一次 HTTP 拿到全部代码）
      * 基金接口不支持批量，但用线程池并发 8 个连接
      * 命中 TTL 缓存的资产先短路，仅未命中部分进入网络请求

    返回 {"updated": N, "skipped": M, "stale": K, "last_refreshed_at": iso}
    """
    from concurrent.futures import ThreadPoolExecutor

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

    # 第一遍：走缓存 + 收集需要联网的 symbol，按 quote_source 分桶
    to_fetch: dict[str, list[tuple[int, str, float]]] = {"stock": [], "fund": []}
    cached_apply: list[tuple[int, QuoteResult]] = []
    for r in rows:
        asset_id = r["id"]
        quote_source = r["quote_source"]
        symbol = (r["symbol"] or "").strip()
        holdings = float(r["holdings"] or 0)
        if not symbol or holdings <= 0 or quote_source not in _AUTO_REFRESH_TYPES:
            skipped += 1
            continue
        if not force:
            cached = _get_cached(db, symbol, QUOTE_TTL_SECONDS)
            if cached is not None:
                cached_apply.append((asset_id, cached))
                continue
        to_fetch[quote_source].append((asset_id, symbol, holdings))

    # 第二遍：批量/并发拉行情
    fresh_results: dict[tuple[str, str], QuoteResult] = {}  # (source, symbol) -> result

    if to_fetch["stock"]:
        symbols = [s for _, s, _ in to_fetch["stock"]]
        for sym, q in _fetch_stock_quotes_batch(symbols).items():
            fresh_results[("stock", sym)] = q

    if to_fetch["fund"]:
        with ThreadPoolExecutor(max_workers=8) as ex:
            fund_symbols = [s for _, s, _ in to_fetch["fund"]]
            for sym, q in zip(fund_symbols, ex.map(_fetch_fund_quote, fund_symbols)):
                if q is not None:
                    fresh_results[("fund", sym)] = q

    # 第三遍：写缓存 + 更新资产 current_value
    for source, items in to_fetch.items():
        for asset_id, symbol, holdings in items:
            q = fresh_results.get((source, symbol))
            if q is None:
                # 外部失败时退到旧缓存（含过期），标记 stale
                cached = _get_cached(db, symbol, max_age=10**9)
                if cached is None:
                    skipped += 1
                    continue
                cached.stale = True
                q = cached
            else:
                _put_cache(db, q, source)
            if q.stale:
                stale += 1
            new_value = round(q.price * holdings, 2)
            _apply_new_value(db, user_id, asset_id, new_value)
            updated += 1

    for asset_id, q in cached_apply:
        # 这些资产 holdings 必然 > 0（前面已过滤），重新查一次以拿到 holdings
        holdings_row = db.execute("SELECT holdings FROM assets WHERE id = ?", (asset_id,)).fetchone()
        holdings = float(holdings_row["holdings"] or 0) if holdings_row else 0.0
        new_value = round(q.price * holdings, 2)
        _apply_new_value(db, user_id, asset_id, new_value)
        updated += 1

    db.commit()
    return {
        "updated": updated,
        "skipped": skipped,
        "stale": stale,
        "last_refreshed_at": _iso_from_epoch(now),
    }


def _apply_new_value(db, user_id: int, asset_id: int, new_value: float) -> None:
    """更新 assets.current_value + 同步写一条 asset_value_history 快照。

    历史快照逻辑被 services/asset_history.snapshot 抽走，让所有改 current_value
    的入口（create / update / sell / refresh-prices）共用一处去重 / 写入逻辑。
    """
    from services.asset_history import snapshot
    now = _iso_now()
    db.execute(
        "UPDATE assets SET current_value = ?, updated_at = ? WHERE id = ?",
        (new_value, now, asset_id),
    )
    snapshot(db, user_id, asset_id, new_value, recorded_at=now)


def _iso_now() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def _iso_from_epoch(ts: int) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")
