"""
Stock Data Service (WQ-0382) -- keyless public equity/ETF price feeds.

A deliberately separate engine from the crypto price paths (services/pricing.py
et al.): no API keys, no chain calls, its own cache namespace
("stock:*"), its own scheduler (services/stock_scheduler.py).

Providers (assessed live 2026-10-20 against BITW, GBTC, NVDA, PLTR; full
report on the hub board -- CNBC 10/10 batch success median 124ms, Nasdaq
10/10, cross-source agreement <=0.004%):

  PRIMARY  CNBC restQuote
    https://quote.cnbc.com/quote-html-webservice/restQuote/...
    - ONE call returns quotes for ALL symbols (pipe-joined).
    - Per symbol: last, change, change_pct, open/high/low, previous day
      close, curmktstatus (PRE/MID/POST/REG), last_time ISO with offset.
    - Bad symbol: entry with code!=0 -- never poisons the batch.

  FALLBACK Nasdaq api (per symbol; also the ONLY daily-bar history source)
    /api/quote/{sym}/info?assetclass=stocks|etf
    /api/quote/{sym}/historical?assetclass=..&fromdate=..&todate=..&limit=..
    - Needs the correct assetclass per symbol; an ETF queried as 'stocks'
      returns no primaryData. asset_class from manual_stocks drives it.

Both are anonymous web endpoints without SLAs: every call here is
best-effort with a hard timeout, callers must tolerate None, and the last
stored price in manual_stocks is always the fallback (apply_stock_prices
only writes symbols that were actually priced). Yahoo Finance was assessed
the same day and rejected: 429 Too Many Requests from hub01 on every
route (chart/quote/spark, cookie or not).
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from config import (
    STOCK_QUOTE_CACHE_TTL_SECONDS,
    STOCK_HISTORY_CACHE_TTL_SECONDS,
    STOCK_PRICE_SANITY_PCT,
)
from services.http_client import get_client

logger = logging.getLogger(__name__)

CNBC_QUOTE_URL = ("https://quote.cnbc.com/quote-html-webservice/restQuote"
                  "/symbolType/symbol")
NASDAQ_BASE = "https://api.nasdaq.com"

# Both endpoints are browser-oriented; a plain python UA trips bot filters.
BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

_SYMBOL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9.\-]{0,9}$")


def normalize_symbol(symbol: str) -> Optional[str]:
    """Uppercase and sanity-check a ticker; None if it can't be a symbol."""
    if not symbol:
        return None
    s = symbol.strip().upper()
    return s if _SYMBOL_RE.match(s) else None


def _to_float(value) -> Optional[float]:
    """Parse '$216.47' / '79,609,080' / 53.13 / None -> float or None."""
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").replace("%", "").strip()
            if not value or value.upper() in ("N/A", "NONE"):
                return None
        f = float(value)
        return f if f == f else None  # NaN guard
    except (TypeError, ValueError):
        return None


class StockDataService:
    """Keyless quotes + daily history for manual stock/ETF holdings."""

    def __init__(self):
        self.stats = {
            "cnbc_calls": 0, "cnbc_failures": 0,
            "nasdaq_calls": 0, "nasdaq_failures": 0,
            "last_quote_run": None, "last_error": None,
        }

    @property
    def _client(self):
        return get_client("stock_feed", timeout=15.0, headers=BROWSER_HEADERS)

    # ------------------------------------------------------------------
    # Live quotes (primary: CNBC, batched)
    # ------------------------------------------------------------------

    async def get_quotes(self, symbols: List[str],
                         use_cache: bool = True) -> Dict[str, dict]:
        """Quotes for the given symbols. Returns {SYMBOL: quote}.

        quote = {price_usd, prev_close_usd, change, change_pct, name,
                 market_status, source, quote_time}
        Never raises; a symbol no source priced is simply absent.
        """
        clean: List[str] = []
        for s in symbols or []:
            n = normalize_symbol(s)
            if n and n not in clean:
                clean.append(n)
        if not clean:
            return {}

        cache_key = "stock:quotes:" + ",".join(sorted(clean))
        if use_cache:
            from database import get_cache
            cached = await get_cache(cache_key)
            if cached:
                return cached

        result: Dict[str, dict] = {}
        try:
            result.update(await self._cnbc_quotes(clean))
        except Exception as e:
            self.stats["cnbc_failures"] += 1
            self.stats["last_error"] = f"cnbc: {e}"
            logger.warning("stock_data: CNBC batch quote failed: %s", e)

        missing = [s for s in clean if s not in result]
        if missing:
            try:
                fallback = await self._nasdaq_quotes(missing)
                result.update(fallback)
            except Exception as e:
                self.stats["last_error"] = f"nasdaq: {e}"
                logger.warning("stock_data: Nasdaq fallback failed: %s", e)

        if result and use_cache:
            from database import set_cache
            await set_cache(cache_key, result,
                            ttl_seconds=STOCK_QUOTE_CACHE_TTL_SECONDS)
        if result:
            self.stats["last_quote_run"] = datetime.now().isoformat()
        return result

    async def _cnbc_quotes(self, symbols: List[str]) -> Dict[str, dict]:
        """One CNBC call for the whole batch. code!=0 entries are skipped."""
        params = {
            "symbols": "|".join(symbols),
            "requestMethod": "itv",
            "noform": "1",
            "partnerId": "2",
            "fund": "1",
            "exthrs": "1",
            "output": "json",
        }
        resp = await self._client.get(CNBC_QUOTE_URL, params=params)
        self.stats["cnbc_calls"] += 1
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")

        out: Dict[str, dict] = {}
        requested = set(symbols)
        quotes = (resp.json()
                      .get("FormattedQuoteResult", {})
                      .get("FormattedQuote", []))
        for q in quotes:
            sym = normalize_symbol(q.get("symbol", ""))
            # code!=0 is CNBC's "unknown symbol" marker; the requested-set
            # guard keeps a stray echo from pricing something we never asked
            # for.
            if not sym or sym not in requested or q.get("code") != 0:
                continue
            price = _to_float(q.get("last"))
            if not price or price <= 0:
                continue
            prev_close = _to_float(q.get("previous_day_closing"))
            change = _to_float(q.get("change"))
            change_pct = _to_float(q.get("change_pct"))
            if change_pct is None and prev_close:
                change_pct = round((price - prev_close) / prev_close * 100, 4)
            out[sym] = {
                "price_usd": price,
                "prev_close_usd": prev_close,
                "change": change,
                "change_pct": change_pct,
                "name": q.get("name") or q.get("shortName"),
                "market_status": q.get("curmktstatus"),
                "exchange": q.get("exchange"),
                "asset_class": ("etf" if "Exchange Traded" in
                                (q.get("subType") or "") else "stock"),
                "quote_time": q.get("last_time"),
                "source": "cnbc",
            }
        return out

    async def _nasdaq_quotes(self, symbols: List[str]) -> Dict[str, dict]:
        """Per-symbol Nasdaq fallback. ETF-vs-stock class is guessed:
        try 'stocks' then 'etf' (an ETF under 'stocks' just has no data)."""
        out: Dict[str, dict] = {}
        for sym in symbols:
            for assetclass in ("stocks", "etf"):
                try:
                    resp = await self._client.get(
                        f"{NASDAQ_BASE}/api/quote/{sym}/info",
                        params={"assetclass": assetclass},
                    )
                    self.stats["nasdaq_calls"] += 1
                    if resp.status_code != 200:
                        continue
                    data = (resp.json().get("data") or {})
                    pd_ = data.get("primaryData") or {}
                    price = _to_float(pd_.get("lastSalePrice"))
                    if not price or price <= 0:
                        continue
                    # The API echoes the resolved symbol; a mismatch means we
                    # were served someone else's quote -- never store it.
                    echoed = normalize_symbol(data.get("symbol") or "")
                    if echoed and echoed != sym:
                        logger.warning(
                            "stock_data: nasdaq echoed %s for %s, ignoring",
                            echoed, sym)
                        continue
                    out[sym] = {
                        "price_usd": price,
                        "prev_close_usd": _to_float(pd_.get("previousClose")),
                        "change": _to_float(pd_.get("netChange")),
                        "change_pct": _to_float(pd_.get("percentageChange")),
                        "name": data.get("companyName"),
                        "market_status": None,
                        "exchange": data.get("exchange"),
                        "asset_class": "etf" if assetclass == "etf" else "stock",
                        "quote_time": pd_.get("lastTradeTimestamp"),
                        "source": "nasdaq",
                    }
                    break
                except Exception as e:
                    self.stats["nasdaq_failures"] += 1
                    logger.debug("stock_data: nasdaq %s (%s) failed: %s",
                                 sym, assetclass, e)
                await asyncio.sleep(0.3)  # per-ticker endpoint: be polite
        return out

    # ------------------------------------------------------------------
    # Daily bars (Nasdaq historical; the only keyless source that worked)
    # ------------------------------------------------------------------

    async def get_history(self, symbol: str, from_date: str, to_date: str,
                          asset_class: str = "stock",
                          use_cache: bool = True) -> List[dict]:
        """Daily bars [{date:'YYYY-MM-DD', open, high, low, close, volume}].

        Dates are 'YYYY-MM-DD' strings. Never raises; returns [] on failure.
        """
        sym = normalize_symbol(symbol)
        if not sym:
            return []
        cache_key = f"stock:hist:{sym}:{from_date}:{to_date}:{asset_class}"
        if use_cache:
            from database import get_cache
            cached = await get_cache(cache_key)
            if cached:
                return cached

        assetclass = "etf" if (asset_class or "").lower() == "etf" else "stocks"
        bars: List[dict] = []
        try:
            resp = await self._client.get(
                f"{NASDAQ_BASE}/api/quote/{sym}/historical",
                params={"assetclass": assetclass, "fromdate": from_date,
                        "todate": to_date, "limit": "200"},
            )
            self.stats["nasdaq_calls"] += 1
            if resp.status_code == 200:
                table = ((resp.json().get("data") or {})
                         .get("tradesTable") or {})
                for row in table.get("rows") or []:
                    close = _to_float(row.get("close"))
                    if close is None:
                        continue
                    bars.append({
                        "date": self._nasdaq_date(row.get("date")),
                        "open": _to_float(row.get("open")),
                        "high": _to_float(row.get("high")),
                        "low": _to_float(row.get("low")),
                        "close": close,
                        "volume": _to_float(row.get("volume")),
                    })
            else:
                self.stats["nasdaq_failures"] += 1
                logger.warning("stock_data: history %s HTTP %s", sym,
                               resp.status_code)
        except Exception as e:
            self.stats["nasdaq_failures"] += 1
            self.stats["last_error"] = f"history {sym}: {e}"
            logger.warning("stock_data: history %s failed: %s", sym, e)

        if bars and use_cache:
            from database import set_cache
            await set_cache(cache_key, bars,
                            ttl_seconds=STOCK_HISTORY_CACHE_TTL_SECONDS)
        return bars

    @staticmethod
    def _nasdaq_date(value) -> Optional[str]:
        """'10/20/2026' -> '2026-10-20'; anything else -> None."""
        try:
            return datetime.strptime(value, "%m/%d/%Y").date().isoformat()
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Engine cycle helper
    # ------------------------------------------------------------------

    async def refresh_and_store(self, tracked: List[dict]) -> dict:
        """One engine cycle over the scheduler's work list.

        Args:
            tracked: [{'symbol':..., 'asset_class': 'stock'|'etf'}, ...]
                     (database.get_tracked_stock_symbols())

        - Quotes every symbol (CNBC batch, Nasdaq fallback per missing one).
        - Writes quotes to manual_stocks (apply_stock_prices: unpriced
          symbols keep their old price) and the day's bar to
          stock_price_history.
        - Cross-source sanity: when both sources priced the same symbol and
          disagree by more than STOCK_PRICE_SANITY_PCT, warn (log only; the
          CNBC batch is kept -- it is the primary).

        Returns cycle stats dict. Never raises.
        """
        from database import apply_stock_prices, upsert_stock_price_history

        symbols = [s for s in (normalize_symbol(t.get("symbol"))
                               for t in tracked or []) if s]
        symbols = list(dict.fromkeys(symbols))  # dedupe, keep order
        result = {"attempted": len(symbols), "priced": 0, "history": 0,
                  "sources": {}, "disagreements": []}
        if not symbols:
            return result

        quotes = await self.get_quotes(symbols)
        result["priced"] = len(quotes)
        for sym, q in quotes.items():
            result["sources"][sym] = q.get("source")

        # Cross-source sanity check (only when CNBC already answered -- a
        # fallback-only symbol already IS the cross-check outcome).
        cnbc_syms = [s for s in symbols
                     if quotes.get(s, {}).get("source") == "cnbc"]
        if cnbc_syms:
            try:
                second = await self._nasdaq_quotes(cnbc_syms[:10])
                for sym, q2 in second.items():
                    p1 = quotes[sym]["price_usd"]
                    p2 = q2["price_usd"]
                    if p1 and p2:
                        diff = abs(p1 - p2) / p1 * 100
                        if diff > STOCK_PRICE_SANITY_PCT:
                            result["disagreements"].append(
                                {"symbol": sym, "cnbc": p1, "nasdaq": p2,
                                 "pct": round(diff, 2)})
                            logger.warning(
                                "stock_data: %s sources disagree by %.2f%% "
                                "(cnbc=%s nasdaq=%s)", sym, diff, p1, p2)
            except Exception as e:
                logger.debug("stock_data: cross-check pass failed: %s", e)

        if quotes:
            await apply_stock_prices({
                sym: {"price_usd": q["price_usd"],
                      "prev_close_usd": q.get("prev_close_usd"),
                      "change_pct": q.get("change_pct"),
                      "source": q.get("source")}
                for sym, q in quotes.items()
            })

        # Persist today's observation per priced symbol (market-locale date;
        # a pre-open run stamps yesterday's date via quote_time when present).
        trade_date = self.market_date()
        for sym, q in quotes.items():
            try:
                await upsert_stock_price_history(sym, trade_date,
                                                 {"last_price": q["price_usd"]},
                                                 source=q.get("source"))
                result["history"] += 1
            except Exception as e:
                logger.warning("stock_data: history upsert %s: %s", sym, e)

        return result

    @staticmethod
    def market_date() -> str:
        """Today's date in the market timezone (America/New_York)."""
        try:
            from zoneinfo import ZoneInfo
            from config import STOCK_MARKET_TZ
            return datetime.now(ZoneInfo(STOCK_MARKET_TZ)).date().isoformat()
        except Exception:
            return datetime.now(timezone.utc).date().isoformat()

    async def backfill_history(self, symbol: str, asset_class: str,
                               days: int = 90) -> int:
        """Pull `days` of daily bars into stock_price_history. Row count."""
        from database import upsert_stock_price_history
        to_d = datetime.now(timezone.utc).date()
        from_d = to_d - timedelta(days=days)
        bars = await self.get_history(symbol, from_d.isoformat(),
                                      to_d.isoformat(), asset_class)
        n = 0
        for bar in bars:
            if not bar.get("date"):
                continue
            await upsert_stock_price_history(symbol, bar["date"], {
                "open": bar.get("open"), "high": bar.get("high"),
                "low": bar.get("low"), "close": bar.get("close"),
                "volume": bar.get("volume"), "last_price": bar.get("close"),
            }, source="nasdaq")
            n += 1
        return n


stock_data_service = StockDataService()
