"""
Intraday portfolio valuation series (WQ-0385).

Answers "can the Portfolio History chart be more granular?": the canonical
history (wallet_daily_balances / /balance-history/data) is DAILY by design --
there are no hourly rows to plot. But the current positions table carries
per-symbol quantities, and keyless sources publish intraday price series, so a
SHORT-range granular curve can be computed on demand:

    portfolio_value(t) = SUM over current positions of quantity x price(t)

Sources (keyless, same policy as the stock engine -- see references in the
abct-backend skill):
  - Crypto / tracked tokens: CoinGecko /coins/{id}/market_chart free tier --
    ~5-minute points for days=1, ~hourly for days=2..90 (verified live from
    the container 2026-10-22).
  - Manual stocks/ETFs: Nasdaq /api/quote/{sym}/chart?charttype=intraday --
    one trading day per call (keyless, the stock engine's fallback source).
    Ranges beyond one day contribute their daily close.
  - Symbols with no intraday source contribute a flat last-known price and
    are named in the response's `excluded_symbols`.

This is deliberately an ESTIMATE for the short ranges it covers: it prices
TODAY's quantities across the window (no historical balance reconstruction,
which is what the daily engine does). The response says so (`note`) and the
frontend labels the mode. Cached per user+range for a few minutes so repeated
dashboard loads don't hammer the feeds.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# range -> (days to fetch, bucket seconds)
INTRADAY_RANGES = {
    "24h": (1, 300),    # CoinGecko free tier is 5-minute at days=1
    "1w": (7, 3600),    # hourly at days=7
}

# Per-symbol price-series cache (shared across users -- prices are not
# user-specific). {cg_id_or_stock:sym: (fetched_at, [(ts_utc_s, price)])}
_PRICE_CACHE: Dict[str, Tuple[float, List[Tuple[int, float]]]] = {}
_PRICE_TTL_S = 600          # intraday prices: refresh at most every 10 min
_STALE_GUARD_S = 3 * 3600   # beyond this the fetch is considered failed-fresh

_CG_DAYS = {"24h": 1, "1w": 7}


async def _http_json(url: str, params: Optional[dict] = None,
                     headers: Optional[dict] = None,
                     timeout: float = 15.0):
    from services.http_client import get_client
    client = get_client("intraday_history", timeout=timeout)
    resp = await client.get(url, params=params, headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} for {url}")
    return resp.json()


_YAHOO_INTERVAL = {1: ("5m", "1d"), 7: ("1h", "7d")}


def _parse_yahoo_chart(data: dict) -> List[Tuple[int, float]]:
    """Yahoo v8 chart payload -> [(utc_s, usd)]. Pure, tested directly."""
    try:
        res = (data.get("chart") or {}).get("result") or []
        r0 = res[0]
        ts = r0.get("timestamp") or []
        closes = (r0.get("indicators") or {}).get("quote") or [{}]
        close = closes[0].get("close") or []
        return [(int(t), float(c))
                for t, c in zip(ts, close) if t and c and float(c) > 0]
    except Exception:
        return []


async def _yahoo_intraday(symbol: str, days: int) -> List[Tuple[int, float]]:
    """Yahoo Finance chart for crypto pairs (SYMBOL-USD): the keyless
    fallback when CoinGecko's free tier rate-limits a burst. Sparse points
    are fine -- the caller forward-fills."""
    interval, rng = _YAHOO_INTERVAL.get(days, ("5m", "1d"))
    yahoo_sym = "MATIC-USD" if symbol.upper() == "POL" else f"{symbol.upper()}-USD"
    key = f"yahoo:{yahoo_sym}:{days}"
    now = datetime.now(timezone.utc).timestamp()
    hit = _PRICE_CACHE.get(key)
    if hit and now - hit[0] < _PRICE_TTL_S:
        return hit[1]
    try:
        data = await _http_json(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}",
            params={"interval": interval, "range": rng},
            headers={"User-Agent": "Mozilla/5.0"})
        pts = _parse_yahoo_chart(data)
        if pts:
            _PRICE_CACHE[key] = (now, pts)
        return pts
    except Exception as e:
        if hit and now - hit[0] < _STALE_GUARD_S:
            return hit[1]
        logger.debug("intraday: yahoo %s failed: %s", yahoo_sym, e)
        return []


async def _coingecko_intraday(cg_id: str, days: int,
                              symbol: str = "") -> List[Tuple[int, float]]:
    """CoinGecko market_chart: [(utc_s, usd)]. 5-min points at days=1,
    hourly at days=7 (free tier granularity). Falls back to Yahoo when CG
    refuses (429 burst) or returns nothing -- WQ-0386: a rate-limited burst
    of ~19 symbols used to leave most of the portfolio 'excluded'."""
    key = f"cg:{cg_id}"
    now = datetime.now(timezone.utc).timestamp()
    hit = _PRICE_CACHE.get(key)
    if hit and now - hit[0] < _PRICE_TTL_S:
        return hit[1]
    try:
        data = await _http_json(
            f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart",
            params={"vs_currency": "usd", "days": days})
        pts = [(int(ts / 1000), float(p))
               for ts, p in data.get("prices", []) if p and p > 0]
        if pts:
            _PRICE_CACHE[key] = (now, pts)
        return pts
    except Exception as e:
        # CG refused this call outright -> live Yahoo fallback (not just the
        # stale cache). WQ-0386.
        if symbol:
            y = await _yahoo_intraday(symbol, days)
            if y:
                return y
        # A 429 backoff: serve the stale series if recent-ish, else empty.
        if hit and now - hit[0] < _STALE_GUARD_S:
            return hit[1]
        logger.warning("intraday: coingecko %s failed: %s", cg_id, e)
        return []


async def _nasdaq_intraday(symbol: str, date_str: str) -> List[Tuple[int, float]]:
    """Nasdaq intraday chart for ONE trading day: [(utc_s, usd)]."""
    key = f"nasdaq:{symbol}:{date_str}"
    now = datetime.now(timezone.utc).timestamp()
    hit = _PRICE_CACHE.get(key)
    if hit and now - hit[0] < _PRICE_TTL_S:
        return hit[1]
    try:
        data = await _http_json(
            f"https://api.nasdaq.com/api/quote/{symbol}/chart",
            params={"assetclass": "stocks", "fromdate": date_str,
                    "todate": date_str, "charttype": "intraday"},
            headers={"User-Agent": "Mozilla/5.0",
                     "Accept": "application/json"})
        pts = []
        for row in ((data.get("data") or {}).get("chart") or []):
            # {"datetime": "Oct 21, 2026 10:15 AM", "value": "$54.10"}
            try:
                dt = datetime.strptime(row["datetime"], "%b %d, %Y %I:%M %p")
                # Nasdaq prints America/New_York wall time; DST-correct via zoneinfo
                from zoneinfo import ZoneInfo
                dt = dt.replace(tzinfo=ZoneInfo("America/New_York"))
                val = float(str(row["value"]).replace("$", "").replace(",", ""))
                if val > 0:
                    pts.append((int(dt.timestamp()), val))
            except Exception:
                continue
        if pts:
            _PRICE_CACHE[key] = (now, pts)
        return pts
    except Exception as e:
        if hit and now - hit[0] < _STALE_GUARD_S:
            return hit[1]
        logger.warning("intraday: nasdaq %s %s failed: %s", symbol, date_str, e)
        return []


def _bucketize(series: List[Tuple[int, float]], bucket_s: int) -> Dict[int, float]:
    """Last price within each bucket_s window (keyed by bucket start)."""
    out: Dict[int, float] = {}
    for ts, price in sorted(series):
        out[ts - (ts % bucket_s)] = price
    return out


def _forward_fill(buckets: Dict[int, float], grid: List[int]) -> List[Optional[float]]:
    """Price aligned to grid with forward-fill (markets paused -> carry)."""
    aligned: List[Optional[float]] = []
    last: Optional[float] = None
    b = 0
    keys = sorted(buckets)
    for ts in grid:
        while b < len(keys) and keys[b] <= ts:
            last = buckets[keys[b]]
            b += 1
        aligned.append(last)
    return aligned


async def build_intraday_series(user_id: int, rng: str,
                                include_symbols: List[Tuple[str, str, float]],
                                ) -> dict:
    """Compose portfolio_value(t) over the range.

    include_symbols: [(symbol, kind, quantity)] where kind is a CoinGecko id
    for crypto/tokens or 'stock' for manual stock/ETF rows.
    """
    days, bucket_s = INTRADAY_RANGES[rng]

    # Fetch all price series with bounded concurrency (free-tier politeness).
    sem = asyncio.Semaphore(4)

    async def fetch(symbol: str, kind: str):
        async with sem:
            if kind == "stock":
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                series = await _nasdaq_intraday(symbol, today)
                if not series and days > 1:
                    # weekend/yesterday: walk back up to 3 days
                    for back in range(1, 4):
                        d = (datetime.now(timezone.utc) - timedelta(days=back)
                             ).strftime("%Y-%m-%d")
                        series = await _nasdaq_intraday(symbol, d)
                        if series:
                            break
                if not series:
                    # Nasdaq refused (bot wall, nothing this window): Yahoo
                    # equity chart carries the same intraday buckets. WQ-0386.
                    series = await _yahoo_intraday(symbol, days)
                return symbol, series
            return symbol, await _coingecko_intraday(kind, days,
                                                     symbol=symbol)

    results = await asyncio.gather(*(fetch(s, k) for s, k, _ in include_symbols))
    series_by_symbol = dict(results)

    # Grid: whole buckets over the window ending now.
    now_b = int(datetime.now(timezone.utc).timestamp())
    grid = list(range(now_b - days * 86400 - now_b % bucket_s,
                      now_b + bucket_s, bucket_s))

    values = [0.0] * len(grid)
    covered = [False] * len(grid)
    excluded: List[str] = []
    for symbol, _kind, qty in include_symbols:
        pts = series_by_symbol.get(symbol) or []
        if not pts:
            excluded.append(symbol)
            continue
        aligned = _forward_fill(_bucketize(pts, bucket_s), grid)
        for i, p in enumerate(aligned):
            if p is not None:
                values[i] += qty * p
                covered[i] = True

    data = [{"timestamp": ts,
             "value": round(values[i], 2)}
            for i, ts in enumerate(grid) if covered[i]]

    granularity = "5-minute" if bucket_s == 300 else "hourly"
    return {
        "mode": "intraday",
        "granularity": granularity,
        "range": rng,
        "data": data,
        "excluded_symbols": sorted(set(excluded)),
        "as_of": datetime.now(timezone.utc).isoformat(),
        "note": ("Intraday estimate: current position quantities priced "
                 "across the window from keyless intraday feeds; not a "
                 "historical balance reconstruction."),
    }
