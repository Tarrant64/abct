"""
Tests for the WQ-0382 stock engine (manual stock/ETF tracking, keyless feed).

Offline by construction: every provider call is monkeypatched against canned
payloads captured live from CNBC/Nasdaq on 2026-10-20 (BITW GBTC NVDA PLTR
assessment -- payloads trimmed, shapes verbatim). The DB side runs against a
real temporary SQLite file so the manual_stocks upsert, the price-write
never-zero rule, the history COALESCE merge, and the scheduler lock are all
genuinely exercised.
"""

import asyncio
import os
import sqlite3
import sys
from datetime import datetime

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402
import services.stock_data as stock_data_module  # noqa: E402
from services.stock_data import (  # noqa: E402
    StockDataService, normalize_symbol, _to_float)
from services.stock_scheduler import parse_refresh_times  # noqa: E402
import routers.stocks as stocks_router  # noqa: E402

USER_ID = 1

# ---------------------------------------------------------------------------
# Canned payloads (captured live 2026-10-20, shapes verbatim)
# ---------------------------------------------------------------------------

CNBC_PAYLOAD = {"FormattedQuoteResult": {"FormattedQuote": [
    {"symbol": "NVDA", "code": 0, "name": "NVIDIA Corporation",
     "shortName": "NVDA", "last": "216.47", "change": "-0.62",
     "change_pct": "-0.29%", "open": "215.98", "high": "218.46",
     "low": "212.77", "previous_day_closing": "217.09",
     "curmktstatus": "POST_MKT", "type": "STOCK",
     "subType": "Common Stock", "exchange": "NASDAQ",
     "last_time": "2026-10-20T16:00:00.000-0400"},
    {"symbol": "BITW", "code": 0, "name": "Bitwise 10 Crypto Index Fund",
     "last": "53.13", "change": "+0.66", "change_pct": "+1.25%",
     "previous_day_closing": "52.47", "curmktstatus": "REG_MKT",
     "type": "STOCK", "subType": "Exchange Traded Fund",
     "exchange": "NYSE Arca", "last_time": "2026-10-20T20:00:00.079-0400"},
    {"symbol": "BADSYM", "code": 1},
]}}

NASDAQ_QUOTE_PAYLOAD = {"data": {
    "symbol": "GBTC", "companyName": "Grayscale Bitcoin Trust (BTC)",
    "exchange": "PSE",
    "primaryData": {"lastSalePrice": "$63.70", "netChange": "+0.56",
                    "percentageChange": "+0.89%", "previousClose": "63.14",
                    "lastTradeTimestamp": "Oct 20, 2026"}}}

NASDAQ_HIST_PAYLOAD = {"data": {
    "symbol": "NVDA", "totalRecords": 2,
    "tradesTable": {
        "headers": {"date": "Date", "close": "Close/Last", "volume": "Volume",
                    "open": "Open", "high": "High", "low": "Low"},
        "rows": [
            {"date": "10/20/2026", "close": "$216.47", "volume": "79,609,080",
             "open": "$215.98", "high": "$218.46", "low": "$212.77"},
            {"date": "10/19/2026", "close": "$217.09", "volume": "98,684,720",
             "open": "$218.095", "high": "$219.62", "low": "$214.70"},
        ]}}}


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeClient:
    """Routes by URL fragment; records calls. Async like httpx.AsyncClient."""
    def __init__(self):
        self.calls = []

    async def get(self, url, params=None, **kw):
        self.calls.append((url, params))
        if "cnbc.com" in url:
            return FakeResponse(200, CNBC_PAYLOAD)
        if "/historical" in url:
            return FakeResponse(200, NASDAQ_HIST_PAYLOAD)
        if "/info" in url:
            assetclass = (params or {}).get("assetclass")
            if "/GBTC/info" in url and assetclass == "etf":
                return FakeResponse(200, NASDAQ_QUOTE_PAYLOAD)
            # 'stocks' lookups and unknown symbols come back without
            # primaryData, like a real ETF-as-stock query.
            return FakeResponse(200, {"data": {"primaryData": {}}})
        return FakeResponse(404, {})


# ---------------------------------------------------------------------------
# DB fixture: real temp SQLite with just the stock engine's tables + locks
# ---------------------------------------------------------------------------

def _make_stock_db(tmp_path):
    db_path = str(tmp_path / "test_stocks.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE manual_stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT NOT NULL,
            name TEXT,
            quantity REAL NOT NULL,
            cost_basis REAL,
            asset_class TEXT DEFAULT 'stock',
            price_usd REAL,
            prev_close_usd REAL,
            change_pct REAL,
            price_source TEXT,
            last_price_update TIMESTAMP,
            include_in_total INTEGER DEFAULT 1,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, symbol)
        )
    """)
    conn.execute("""
        CREATE TABLE stock_price_history (
            symbol TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            last_price REAL,
            source TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, trade_date)
        )
    """)
    conn.execute("""
        CREATE TABLE cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE scheduler_locks (
            lock_name TEXT PRIMARY KEY,
            holder TEXT NOT NULL,
            acquired_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def stock_db(tmp_path, monkeypatch):
    db_path = _make_stock_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    return db_path


@pytest.fixture
def fake_feed(monkeypatch):
    """No test may touch the real network through the stock client."""
    client = FakeClient()
    monkeypatch.setattr(stock_data_module, "get_client",
                        lambda *a, **k: client)
    return client


# ---------------------------------------------------------------------------
# Pure parsers
# ---------------------------------------------------------------------------

def test_to_float_handles_market_strings():
    assert _to_float("$216.47") == 216.47
    assert _to_float("79,609,080") == 79609080.0
    assert _to_float("+1.25%") == 1.25
    assert _to_float("N/A") is None
    assert _to_float(None) is None
    assert _to_float("") is None
    assert _to_float(53.13) == 53.13


def test_normalize_symbol():
    assert normalize_symbol(" nvda ") == "NVDA"
    assert normalize_symbol("BRK.B") == "BRK.B"
    assert normalize_symbol("") is None
    assert normalize_symbol("1NVDA") is None
    assert normalize_symbol("NOPE;DROP TABLE") is None
    assert normalize_symbol("TOOLONGSYMBOL123") is None


def test_nasdaq_date():
    assert StockDataService._nasdaq_date("10/20/2026") == "2026-10-20"
    assert StockDataService._nasdaq_date("junk") is None


# ---------------------------------------------------------------------------
# Feed parsing
# ---------------------------------------------------------------------------

def test_cnbc_batch_parse_skips_bad_symbols(stock_db, fake_feed):
    svc = StockDataService()
    quotes = asyncio.run(svc.get_quotes(
        ["NVDA", "BITW", "BADSYM", "TOOLONGSYMBOL123"], use_cache=False))
    assert set(quotes) == {"NVDA", "BITW"}           # code=1 skipped
    # the too-long junk symbol never even reaches the feed (client-side
    # validation); the one real CNBC call carries only valid symbols
    assert fake_feed.calls[0][1]["symbols"] == "NVDA|BITW|BADSYM"
    nvda = quotes["NVDA"]
    assert nvda["price_usd"] == 216.47
    assert nvda["prev_close_usd"] == 217.09
    assert nvda["change_pct"] == -0.29
    assert nvda["market_status"] == "POST_MKT"
    assert nvda["source"] == "cnbc"
    bitw = quotes["BITW"]
    assert bitw["asset_class"] == "etf"              # subType drives it
    assert bitw["change_pct"] == 1.25


def test_nasdaq_fallback_only_for_missing(stock_db, fake_feed):
    svc = StockDataService()
    # CNBC payload only prices NVDA/BITW; GBTC must come from the fallback,
    # and the fallback must retry with assetclass=etf after 'stocks' comes
    # back empty.
    quotes = asyncio.run(svc.get_quotes(["NVDA", "GBTC"], use_cache=False))
    assert quotes["GBTC"]["price_usd"] == 63.70
    assert quotes["GBTC"]["source"] == "nasdaq"
    assert quotes["GBTC"]["asset_class"] == "etf"
    classes = [p.get("assetclass") for u, p in fake_feed.calls
               if "/info" in u]
    assert classes == ["stocks", "etf"]


def test_history_parse(stock_db, fake_feed):
    svc = StockDataService()
    bars = asyncio.run(svc.get_history("NVDA", "2026-10-01", "2026-10-20",
                                       use_cache=False))
    assert len(bars) == 2
    assert bars[0]["date"] == "2026-10-20"
    assert bars[0]["close"] == 216.47
    assert bars[0]["volume"] == 79609080.0


def test_feed_total_failure_returns_empty(stock_db, monkeypatch):
    class Boom:
        async def get(self, *a, **k):
            raise RuntimeError("network down")
    monkeypatch.setattr(stock_data_module, "get_client", lambda *a, **k: Boom())
    svc = StockDataService()
    assert asyncio.run(svc.get_quotes(["NVDA"], use_cache=False)) == {}


# ---------------------------------------------------------------------------
# DB layer
# ---------------------------------------------------------------------------

def test_manual_stock_crud_roundtrip(stock_db):
    async def scenario():
        sid = await database.add_manual_stock(
            {"symbol": "nvda", "quantity": 10, "cost_basis": 150.0,
             "price_usd": 216.47, "price_source": "cnbc",
             "description": "Fidelity"}, USER_ID)
        row = await database.get_manual_stock_by_id(sid, USER_ID)
        assert row["symbol"] == "NVDA"
        assert row["price_usd"] == 216.47
        assert row["last_price_update"] is not None
        assert row["description"] == "Fidelity"

        # same symbol again: quantity replaces, price survives
        sid2 = await database.add_manual_stock(
            {"symbol": "NVDA", "quantity": 12}, USER_ID)
        row = await database.get_manual_stock_by_id(sid2, USER_ID)
        assert row["quantity"] == 12 and row["price_usd"] == 216.47
        assert row["description"] == "Fidelity"  # COALESCE keeps the note
        assert len(await database.get_all_manual_stocks(USER_ID)) == 1

        await database.update_manual_stock(sid, {"quantity": 7, "bogus": 1},
                                           USER_ID)
        row = await database.get_manual_stock_by_id(sid, USER_ID)
        assert row["quantity"] == 7

        # WQ-0384 edit path: description updates and can be cleared to NULL
        await database.update_manual_stock(sid, {"description": "Wells Fargo"},
                                           USER_ID)
        row = await database.get_manual_stock_by_id(sid, USER_ID)
        assert row["description"] == "Wells Fargo"
        await database.update_manual_stock(sid, {"description": None}, USER_ID)
        row = await database.get_manual_stock_by_id(sid, USER_ID)
        assert row["description"] is None

        # user scoping: another user cannot see/touch it
        assert await database.get_manual_stock_by_id(sid, 999) is None
        await database.delete_manual_stock(sid, 999)
        assert await database.get_manual_stock_by_id(sid, USER_ID) is not None
        await database.delete_manual_stock(sid, USER_ID)
        assert await database.get_all_manual_stocks(USER_ID) == []
    asyncio.run(scenario())


def test_apply_stock_prices_never_zeroes(stock_db):
    async def scenario():
        await database.add_manual_stock(
            {"symbol": "NVDA", "quantity": 1, "price_usd": 200.0,
             "price_source": "cnbc"}, USER_ID)
        await database.add_manual_stock(
            {"symbol": "PLTR", "quantity": 1, "price_usd": 180.0,
             "price_source": "cnbc"}, USER_ID)
        # Engine priced only NVDA this cycle.
        await database.apply_stock_prices({"NVDA": {
            "price_usd": 216.47, "prev_close_usd": 217.09,
            "change_pct": -0.29, "source": "cnbc"}})
        nvda = await database.get_manual_stock_by_symbol("NVDA", USER_ID)
        pltr = await database.get_manual_stock_by_symbol("PLTR", USER_ID)
        assert nvda["price_usd"] == 216.47
        assert nvda["last_price_update"] is not None
        assert pltr["price_usd"] == 180.0          # untouched, not zeroed
    asyncio.run(scenario())


def test_tracked_symbols_etf_class_wins(stock_db):
    async def scenario():
        await database.add_manual_stock({"symbol": "BITW", "quantity": 1,
                                         "asset_class": "stock"}, USER_ID)
        await database.add_manual_stock({"symbol": "BITW", "quantity": 2,
                                         "asset_class": "etf"}, 2)
        await database.add_manual_stock({"symbol": "NVDA", "quantity": 1},
                                        USER_ID)
        tracked = await database.get_tracked_stock_symbols()
        assert tracked == [{"symbol": "BITW", "asset_class": "etf"},
                           {"symbol": "NVDA", "asset_class": "stock"}]
    asyncio.run(scenario())


def test_history_upsert_coalesce_and_order(stock_db):
    async def scenario():
        # intraday observation: last_price only
        await database.upsert_stock_price_history(
            "NVDA", "2026-10-20", {"last_price": 215.0}, source="cnbc")
        # close run: full OHLC lands, must not wipe last_price
        await database.upsert_stock_price_history(
            "NVDA", "2026-10-20",
            {"open": 215.98, "high": 218.46, "low": 212.77,
             "close": 216.47, "volume": 79609080}, source="nasdaq")
        await database.upsert_stock_price_history(
            "NVDA", "2026-10-19", {"close": 217.09}, source="nasdaq")
        bars = await database.get_stock_price_history("NVDA", 90)
        assert [b["trade_date"] for b in bars] == ["2026-10-19", "2026-10-20"]
        today = bars[1]
        assert today["close"] == 216.47 and today["last_price"] == 215.0
    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# Cycle + scheduler
# ---------------------------------------------------------------------------

def test_refresh_and_store_writes_prices_and_history(stock_db, fake_feed):
    async def scenario():
        await database.add_manual_stock({"symbol": "NVDA", "quantity": 2},
                                        USER_ID)
        await database.add_manual_stock({"symbol": "GBTC", "quantity": 5,
                                         "asset_class": "etf"}, USER_ID)
        svc = StockDataService()
        stats = await svc.refresh_and_store(
            [{"symbol": "NVDA", "asset_class": "stock"},
             {"symbol": "GBTC", "asset_class": "etf"}])
        assert stats["attempted"] == 2 and stats["priced"] == 2
        assert stats["sources"] == {"NVDA": "cnbc", "GBTC": "nasdaq"}
        nvda = await database.get_manual_stock_by_symbol("NVDA", USER_ID)
        assert nvda["price_usd"] == 216.47
        assert nvda["price_source"] == "cnbc"
        gbtc = await database.get_manual_stock_by_symbol("GBTC", USER_ID)
        assert gbtc["price_usd"] == 63.70
        hist = await database.get_stock_price_history("NVDA", 5)
        assert hist and hist[-1]["last_price"] == 216.47
    asyncio.run(scenario())


def test_parse_refresh_times_validation():
    assert parse_refresh_times("09:35,12:00,16:05") == [
        {"hour": 9, "minute": 35}, {"hour": 12, "minute": 0},
        {"hour": 16, "minute": 5}]
    assert parse_refresh_times("09:35,bogus,25:00,16:05") == [
        {"hour": 9, "minute": 35}, {"hour": 16, "minute": 5}]
    # total garbage falls back to the user's 3-slot spec, not zero slots
    assert len(parse_refresh_times("nonsense")) == 3


def test_scheduler_cron_three_weekday_runs_et(stock_db, monkeypatch):
    """The 3 slots fire at the right ET wall-clock times, weekdays only.
    The trigger carries the market timezone itself (recomputed per fire),
    which is what keeps the slots correct across DST transitions."""
    from services.stock_scheduler import StockSchedulerService
    svc = StockSchedulerService()
    svc.enabled = True

    async def scenario():
        await svc.start()
        jobs = svc.scheduler.get_jobs()
        assert len(jobs) == 3
        runs = sorted(j.next_run_time for j in jobs)
        assert all(str(r.tzinfo) == "America/New_York" for r in runs)
        wall = sorted((r.hour, r.minute) for r in runs)
        assert wall == [(9, 35), (12, 0), (16, 5)]
        assert all(r.weekday() < 5 for r in runs)
        await svc.stop()
    asyncio.run(scenario())


def test_scheduler_run_cycle_lock_and_stats(stock_db, monkeypatch):
    """run_cycle takes the advisory lock, calls the feed once, writes stats,
    and a second holder is skipped."""
    from services.stock_scheduler import StockSchedulerService
    svc = StockSchedulerService()

    calls = []

    async def fake_refresh(tracked):
        calls.append(tracked)
        return {"attempted": 1, "priced": 1, "history": 1,
                "sources": {"NVDA": "cnbc"}, "disagreements": []}

    monkeypatch.setattr("services.stock_scheduler.stock_data_service."
                        "refresh_and_store", fake_refresh)
    asyncio.run(database.add_manual_stock({"symbol": "NVDA", "quantity": 1},
                                          USER_ID))
    stats = asyncio.run(svc.run_cycle(reason="test"))
    assert stats["priced"] == 1 and calls[0][0]["symbol"] == "NVDA"
    assert svc.stats["last_attempted"] == 1 and svc.stats["last_priced"] == 1

    # lock held elsewhere -> skip, no feed call
    other = StockSchedulerService()
    import database as db
    assert asyncio.run(db.try_acquire_scheduler_lock(
        "stock_price_refresh", "thief", ttl_seconds=600))
    before = len(calls)
    out = asyncio.run(other.run_cycle())
    assert out == {"skipped": "lock"} and len(calls) == before


# ---------------------------------------------------------------------------
# Router helpers
# ---------------------------------------------------------------------------

def test_enrich_value_and_pnl_math():
    row = {"id": 1, "symbol": "NVDA", "name": "NVIDIA Corporation",
           "quantity": 10, "cost_basis": 150.0, "asset_class": "stock",
           "price_usd": 200.0, "prev_close_usd": 199.0, "change_pct": 0.5,
           "price_source": "cnbc", "last_price_update":
               datetime(2026, 10, 20, 21, 5), "include_in_total": 1}
    out = stocks_router._enrich(row, {})
    assert out["value_usd"] == 2000.0
    assert out["cost_value_usd"] == 1500.0
    assert out["unrealized_pnl_usd"] == 500.0
    assert out["unrealized_pnl_pct"] == 33.33
    assert out["last_price_update"] == "2026-10-20T21:05:00"  # naive UTC

    # live quote overrides the stored row
    out2 = stocks_router._enrich(row, {"NVDA": {"price_usd": 216.47,
                                                "change_pct": -0.29,
                                                "market_status": "POST_MKT",
                                                "source": "cnbc",
                                                "name": None}})
    assert out2["price_usd"] == 216.47 and out2["change_pct"] == -0.29
    assert out2["value_usd"] == 2164.7


def test_add_request_validators():
    from pydantic import ValidationError
    req = stocks_router.StockAddRequest(symbol=" nvda ", quantity=3)
    assert req.symbol == "NVDA"
    with pytest.raises(ValidationError):
        stocks_router.StockAddRequest(symbol="NVDA", quantity=0)
    with pytest.raises(ValidationError):
        stocks_router.StockAddRequest(symbol="BAD SYMBOL", quantity=1)
    with pytest.raises(ValidationError):
        stocks_router.StockAddRequest(symbol="NVDA", quantity=1,
                                      asset_class="crypto")
