"""
WQ-0386: stocks everywhere the portfolio value is shown.

Covers the daily-history stock overlay math (services/stock_history), the
Yahoo intraday fallback parser, the endpoint wiring pins (overlay applied +
cache keys versioned so pre-stock rows are never served), and the mobile
summary/top_holdings/all-holdings stocks merge. The pure cores run directly;
the FastAPI paths are exercised where existing fixtures make that cheap,
otherwise pinned at source level like the neighboring contract tests.
"""

import os
import sys

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "backend"))

from services.stock_history import build_stock_daily_values  # noqa: E402
from services.intraday_history import _parse_yahoo_chart  # noqa: E402


def _read(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as f:
        return f.read()


def _bitw_stock(**over):
    row = {
        "symbol": "BITW", "quantity": 10.0, "price_usd": 50.0,
        "created_at": "2026-01-05 10:00:00", "include_in_total": 1,
    }
    row.update(over)
    return row


def _bars(days_prices):
    return [{"trade_date": d, "close": p} for d, p in days_prices]


# ------------------------------------------------------- stock_history core

def test_daily_values_uses_close_per_date():
    bars = _bars([("2026-01-05", 40.0), ("2026-01-06", 42.0)])
    out = build_stock_daily_values([_bitw_stock()], {"BITW": bars})
    assert out["2026-01-05"] == 400.0   # 10 x 40
    assert out["2026-01-06"] == 420.0   # 10 x 42


def test_created_at_floor_hides_earlier_bars():
    bars = _bars([("2026-01-01", 30.0), ("2026-01-05", 40.0)])
    out = build_stock_daily_values([_bitw_stock()], {"BITW": bars})
    assert "2026-01-01" not in out  # held before the user added it: unknown
    assert out["2026-01-05"] == 400.0


def test_weekend_gaps_forward_fill_last_close():
    bars = _bars([("2026-01-09", 40.0), ("2026-01-12", 44.0)])  # Fri -> Mon
    out = build_stock_daily_values([_bitw_stock()], {"BITW": bars})
    assert out["2026-01-10"] == 400.0  # Sat carries Fri's close
    assert out["2026-01-11"] == 400.0  # Sun carries Fri's close
    assert out["2026-01-12"] == 440.0


def test_current_price_carries_past_last_bar():
    bars = _bars([("2026-01-05", 40.0), ("2026-01-06", 42.0)])
    out = build_stock_daily_values([_bitw_stock()], {"BITW": bars})
    today_key = max(out)
    assert out[today_key] == 500.0  # 10 x price_usd 50 on every day after
    assert out["2026-01-07"] == 500.0


def test_include_in_total_zero_is_excluded():
    out = build_stock_daily_values(
        [_bitw_stock(include_in_total=0)], {"BITW": _bars([("2026-01-05", 40.0)])})
    assert out == {}


def test_no_bars_falls_back_to_stored_price_today_only():
    out = build_stock_daily_values([_bitw_stock()], {})
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert out == {today: 500.0}


def test_start_date_filters_backfill():
    bars = _bars([("2026-01-05", 40.0), ("2026-01-06", 42.0)])
    out = build_stock_daily_values([_bitw_stock()], {"BITW": bars},
                                   start_date="2026-01-06")
    assert "2026-01-05" not in out
    assert out["2026-01-06"] == 420.0


def test_multiple_stocks_sum_per_date():
    a = _bitw_stock()
    b = _bitw_stock(symbol="NVDA", quantity=2.0, price_usd=100.0,
                    created_at="2026-01-05")
    bars = {"BITW": _bars([("2026-01-05", 40.0)]),
            "NVDA": _bars([("2026-01-05", 90.0)])}
    out = build_stock_daily_values([a, b], bars)
    assert out["2026-01-05"] == 400.0 + 180.0


# ------------------------------------------------- yahoo fallback parser

def test_parse_yahoo_chart_basic():
    payload = {"chart": {"result": [{
        "timestamp": [100, 200, 300],
        "indicators": {"quote": [{"close": [1.5, None, 2.5]}]},
    }]}}
    assert _parse_yahoo_chart(payload) == [(100, 1.5), (300, 2.5)]


def test_parse_yahoo_chart_malformed_is_empty():
    assert _parse_yahoo_chart({}) == []
    assert _parse_yahoo_chart({"chart": {"result": []}}) == []


# ------------------------------------------------------ endpoint wiring pins

def test_daily_chart_paths_overlay_stocks_and_bump_cache_keys():
    src = _read("backend", "routers", "portfolio.py")
    assert "stocks_map = await _stock_chart_overlay(user_id, start_date)" in src
    assert 'comps["stocks"] = round(sv, 2)' in src
    assert '"unified_chart_v2_' in src, "chart cache key must be versioned"
    assert '"portfolio_24h_hourly_v2_' in src
    assert '"all_holdings_v2_' in src
    # 24h hourly carries stocks as the static off-chain offset
    assert "stocks_usd = float(totals.get('manual_stocks_usd'" in src
    assert "+ stocks_usd" in src


def test_balance_history_daily_overlay():
    src = _read("backend", "routers", "balance_history.py")
    assert "from services.stock_history import stock_daily_values" in src
    assert "point['value'] = round(point['value'] + sv, 2)" in src


def test_intraday_stock_and_crypto_fallbacks_wired():
    src = _read("backend", "services", "intraday_history.py")
    assert "await _yahoo_intraday(symbol, days)" in src  # stock + crypto fallback
    assert "symbol=symbol" in src  # CG fallback gets the raw symbol
    assert "query1.finance.yahoo.com/v8/finance/chart" in src


def test_mobile_summary_includes_stocks():
    src = _read("backend", "routers", "mobile.py")
    assert "stocks_value = float(snapshot_totals.get('manual_stocks_usd'" in src
    assert "stocks_value)" in src and "+\n                       stocks_value" in src, \
        "total must fold stocks in"
    assert '"stocks": {' in src, "breakdown.stocks bucket"
    assert "mobile_portfolio_summary_v2_" in src
    assert "mobile_breakdown_history_v2_" in src
    assert "Could not merge manual stocks into top_holdings" in src


def test_all_holdings_returns_stock_rows_server_side():
    src = _read("backend", "routers", "portfolio.py")
    assert "'source': 'manual_stock'," in src
    # the v2 client append must de-dup against server-provided rows now
    app = _read("frontend", "v2", "js", "v2-app.js")
    assert "_seenSyms[String(s.symbol || '').toUpperCase()]" in app


# ------------------------------------------------ mobile instant via stubs

def test_instant_includes_manual_stock_from_manual_stocks(monkeypatch):
    """/portfolio/instant must carry stocks even when the positions table has
    none (mobile reads /instant without ever running the summary pass)."""
    import database
    import routers.portfolio as portfolio

    async def _no_positions(user_id):
        return []

    async def _no_freshness(user_id):
        return {}

    async def _stocks(user_id=None):
        return [{"symbol": "BITW", "quantity": 10.0, "price_usd": 50.0,
                 "include_in_total": 1, "change_pct": 1.2, "name": "Bitwise"}]

    monkeypatch.setattr(database, "get_all_portfolio_positions", _no_positions)
    monkeypatch.setattr(database, "get_positions_freshness", _no_freshness)
    monkeypatch.setattr(database, "get_all_manual_stocks", _stocks)
    monkeypatch.setattr(portfolio, "get_nft_inclusion_preference",
                        _false_pref())

    # no SQLite in this test: metadata_cache getters answer "no metadata"
    # (same pattern as test_summary_cache_variants._stub_metadata_cache)
    async def _no_meta(symbol):
        return None
    monkeypatch.setattr(portfolio.metadata_cache, "get_metadata", _no_meta)

    async def _run():
        return await portfolio.get_portfolio_instant(user_id=7)

    # positions empty -> early return must NOT skip the stocks block: with
    # only stocks present the endpoint still reports has_positions True.
    import asyncio
    data = asyncio.run(_run())
    assert data["total_usd"] == pytest.approx(500.0)
    assert data["breakdown"].get("manual_stock") == pytest.approx(500.0)
    syms = [h["symbol"] for h in data["top_holdings"]]
    assert "BITW" in syms
    assert data["has_positions"] is True


def _false_pref():
    async def _inner(user_id):
        return False
    return _inner
