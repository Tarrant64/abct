"""
Daily stock-value overlay for the canonical portfolio history (WQ-0386).

The chart totals (wallet_daily_balances -> /balance-history/data,
/portfolio/history unified chart, mobile chart endpoints) are collected from
wallet sources only — manual stock/ETF holdings were never part of them, so
the line undershot the headline total for every user with stocks.

This module reconstructs a per-date stock component from the stock engine's
own daily bars (stock_price_history, backfilled + updated 3x/day by
services/stock_scheduler.py), applying two honesty floors:

  * a holding only contributes from its created_at date forward (ABCT does
    not know when the user actually bought; anything earlier is a guess),
  * weekend/holiday gaps forward-fill from the last known close (markets
    were closed; the portfolio did not drop to zero), and the current
    engine price carries the fill through to today.

Dates with no information at all stay absent from the map — callers add
nothing there rather than invent a value.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def build_stock_daily_values(stocks: list,
                             bars_by_symbol: Dict[str, list],
                             start_date: Optional[str] = None,
                             end_date: Optional[str] = None) -> Dict[str, float]:
    """Pure core: date -> summed stock value (USD).

    stocks: manual_stocks rows (symbol, quantity, price_usd, created_at,
            include_in_total). bars_by_symbol: symbol -> list of
    stock_price_history rows (oldest first, each with trade_date + close /
    last_price).
    """
    out: Dict[str, float] = {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for s in stocks:
        if s.get("include_in_total", 1) != 1:
            continue
        symbol = (s.get("symbol") or "").strip().upper()
        try:
            qty = float(s.get("quantity") or 0)
        except (TypeError, ValueError):
            continue
        if not symbol or qty <= 0:
            continue
        created = (str(s.get("created_at") or ""))[:10]

        # date -> price series (close preferred, last_price as backup)
        series = []
        for b in bars_by_symbol.get(symbol) or []:
            d = (b.get("trade_date") or "")[:10]
            px = b.get("close")
            if px in (None, 0):
                px = b.get("last_price")
            if d and px:
                series.append((d, float(px)))
        series.sort()
        if created:
            series = [(d, p) for d, p in series if d >= created]

        if series:
            for d, p in series:
                if start_date and d < start_date:
                    continue
                if end_date and d > end_date:
                    continue
                out[d] = out.get(d, 0.0) + qty * p
            first_d, last_d = series[0][0], series[-1][0]
            # Forward-fill trading gaps between first and last bar (weekends
            # and holidays: the last close carries through).
            if len(series) > 1:
                cur = datetime.strptime(first_d, "%Y-%m-%d")
                d1 = datetime.strptime(last_d, "%Y-%m-%d")
                idx = 0
                last_px = series[0][1]
                while cur <= d1:
                    ds = cur.strftime("%Y-%m-%d")
                    while idx < len(series) and series[idx][0] <= ds:
                        last_px = series[idx][1]
                        idx += 1
                    if ds not in out and (not start_date or ds >= start_date) \
                            and (not end_date or ds <= end_date):
                        out[ds] = out.get(ds, 0.0) + qty * last_px
                    cur += timedelta(days=1)
            # Carry the current engine price forward through any date after
            # the last stored bar (stale bars -> the chart keeps moving with
            # the 3x/day engine instead of freezing at an old close).
            try:
                cur_price = float(s.get("price_usd") or 0)
            except (TypeError, ValueError):
                cur_price = 0.0
            if cur_price > 0:
                cap = min(today, end_date) if end_date else today
                cur = datetime.strptime(last_d, "%Y-%m-%d") + timedelta(days=1)
                cap_dt = datetime.strptime(cap, "%Y-%m-%d")
                while cur <= cap_dt:
                    ds = cur.strftime("%Y-%m-%d")
                    if ds not in out and (not start_date or ds >= start_date):
                        out[ds] = out.get(ds, 0.0) + qty * cur_price
                    cur += timedelta(days=1)
        else:
            # No bars at all: the engine's stored price from created_at on.
            try:
                cur_price = float(s.get("price_usd") or 0)
            except (TypeError, ValueError):
                cur_price = 0.0
            if cur_price > 0 and created and (not start_date or today >= start_date):
                out[today] = out.get(today, 0.0) + qty * cur_price
    return {d: round(v, 6) for d, v in out.items()}


async def stock_daily_values(user_id: int, start_date: Optional[str] = None,
                             end_date: Optional[str] = None) -> Dict[str, float]:
    """Fetch stocks + bars from the DB and return date -> stock value."""
    try:
        from database import (get_all_manual_stocks,
                              get_stock_price_history)
        stocks = await get_all_manual_stocks(user_id=user_id)
        if not stocks:
            return {}
        bars = {}
        for s in stocks:
            sym = (s.get("symbol") or "").strip().upper()
            if sym:
                bars[sym] = await get_stock_price_history(sym, days=3650)
        return build_stock_daily_values(stocks, bars,
                                        start_date=start_date,
                                        end_date=end_date)
    except Exception as e:
        logger.debug("stock_daily_values failed (chart proceeds without "
                     "stocks): %s", e)
        return {}
