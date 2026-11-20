"""
Server-fixes item 7 (2026-11-20): /api/mobile/analytics/fees and
/api/mobile/analytics/staking-income -- bounded SQL aggregates over stored
rows, cached (stable ETag -> 304), never fabricating data.
"""

import os
import sqlite3
import sys
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402
import routers.mobile as mobile  # noqa: E402
from auth_utils import verify_session  # noqa: E402
from services import mobile_analytics  # noqa: E402

NOW = datetime.now(timezone.utc)
THIS_MONTH = NOW.strftime("%Y-%m")
OLD = "2019-01-15 10:00:00"          # far outside any window
RECENT = NOW.strftime("%Y-%m-%d") + " 08:00:00"

SCHEMA = """
CREATE TABLE transaction_history (
    id INTEGER PRIMARY KEY, user_id INTEGER, wallet_id INTEGER, blockchain TEXT,
    tx_hash TEXT, tx_time TIMESTAMP, direction TEXT, amount TEXT, token_symbol TEXT,
    fee TEXT, status TEXT DEFAULT 'confirmed');
CREATE TABLE exchange_transactions (
    id INTEGER PRIMARY KEY, user_id INTEGER, exchange TEXT, tx_id TEXT, tx_type TEXT,
    status TEXT DEFAULT 'completed', tx_time TIMESTAMP, amount TEXT, token_symbol TEXT,
    native_amount TEXT, native_currency TEXT DEFAULT 'USD', fee TEXT, fee_currency TEXT);
"""

PRICES = {"ADA": {"usd": 0.5}, "ETH": {"usd": 3000.0}, "BTC": {"usd": 100000.0}}
NATIVE = {"cardano": "ADA", "ethereum": "ETH", "bitcoin": "BTC"}


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "a.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    th = [
        # (user, chain, hash, time, direction, token, fee, status)
        (1, "cardano", "h1", RECENT, "sent", "ADA", "0.2", "confirmed"),
        (1, "cardano", "h1", RECENT, "sent", "SNEK", "0.2", "confirmed"),   # same tx, 2nd token row
        (1, "cardano", "h2", RECENT, "received", "ADA", "0.17", "confirmed"),  # counterparty paid
        (1, "ethereum", "e1", RECENT, "sent", "ETH", "0.001", "failed"),    # failed tx still paid gas
        (1, "ethereum", "e0", OLD, "sent", "ETH", "5", "confirmed"),        # out of window
        (1, "bitcoin", "b1", RECENT, "sent", "BTC", "0.00001", "confirmed"),
        (1, "dogecoin", "d1", RECENT, "sent", "DOGE", "1", "confirmed"),    # no price -> unpriced
        (2, "cardano", "x1", RECENT, "sent", "ADA", "99", "confirmed"),     # other user
    ]
    conn.executemany("INSERT INTO transaction_history (user_id, wallet_id, blockchain, tx_hash, tx_time, direction, token_symbol, fee, status) VALUES (?,1,?,?,?,?,?,?,?)", th)
    ex = [
        # (user, exchange, id, type, time, amount, token, native_amount, native_cur, fee, fee_cur)
        (1, "coinbase", "t1", "buy", RECENT, "1", "ETH", "3000", "USD", "1.5", "USD"),
        (1, "bybit", "t2", "sell", RECENT, "1", "ADA", "0.5", "USD", "0.001", "BTC"),
        (1, "coinbase", "r1", "staking_reward", RECENT, "2", "ETH", "6000", "USD", "", ""),
        (1, "coinbase", "r2", "staking_reward", RECENT, "100", "ADA", "", "USD", "", ""),  # no recorded USD
        (1, "coinbase", "r0", "staking_reward", OLD, "1", "ETH", "10", "USD", "", ""),    # outside window
        (2, "coinbase", "r9", "staking_reward", RECENT, "9", "ETH", "9", "USD", "", ""),
    ]
    conn.executemany("INSERT INTO exchange_transactions (user_id, exchange, tx_id, tx_type, tx_time, amount, token_symbol, native_amount, native_currency, fee, fee_currency) VALUES (?,?,?,?,?,?,?,?,?,?,?)", ex)
    conn.commit()
    conn.close()
    monkeypatch.setattr(database, "DATABASE_PATH", path)
    return path


async def test_fees_dedupe_sender_only_window_and_conversion(db):
    out = await mobile_analytics.fees_summary(1, 12, PRICES, NATIVE)
    chains = {c["chain"]: c for c in out["by_chain"]}
    # cardano: ONE 0.2 ADA fee for h1 (two token rows), h2 (received) ignored
    assert chains["cardano"]["native_amount"] == pytest.approx(0.2)
    assert chains["cardano"]["usd"] == pytest.approx(0.1)
    assert chains["cardano"]["tx_count"] == 1
    assert chains["ethereum"]["usd"] == pytest.approx(3.0)       # failed tx counted, old tx not
    assert chains["bitcoin"]["usd"] == pytest.approx(1.0)
    ex = {e["exchange_id"]: e for e in out["by_exchange"]}
    assert ex["coinbase"]["usd"] == pytest.approx(1.5)           # USD fee exact
    assert ex["bybit"]["usd"] == pytest.approx(100.0)            # 0.001 BTC at current price
    assert out["total_usd"] == pytest.approx(0.1 + 3.0 + 1.0 + 1.5 + 100.0)
    # months: everything recent lands in this month
    assert [m["month"] for m in out["by_month"]] == [THIS_MONTH]
    assert out["by_month"][0]["usd"] == pytest.approx(out["total_usd"])
    # honesty flags
    assert out["price_basis"] == "current" and out["approximate"] is True
    assert [u["symbol"] for u in out["unpriced"]] == ["dogecoin"]   # no native symbol mapped
    assert out["generated_at"].endswith("Z")


async def test_fees_other_user_isolated(db):
    out = await mobile_analytics.fees_summary(2, 12, PRICES, NATIVE)
    assert out["total_usd"] == pytest.approx(99 * 0.5)


async def test_staking_income_from_stored_rewards_only(db):
    out = await mobile_analytics.staking_income_summary(1, 12, PRICES)
    assert out["count"] == 2                                   # old + other user's rows excluded
    # r1 has a recorded USD value (6000); r2 has none -> 100 ADA at current price 0.5
    assert out["total_usd"] == pytest.approx(6000.0 + 50.0)
    assert out["approximate"] is True                          # r2 used the current price
    assets = {a["symbol"]: a for a in out["by_asset"]}
    assert assets["ETH"]["usd"] == pytest.approx(6000.0)
    assert assets["ADA"]["amount"] == pytest.approx(100.0)
    assert out["available_from"] == "2019-01-15"               # earliest stored reward row
    srcs = {s["source"]: s for s in out["sources"]}
    assert srcs["exchange"]["available"] is True
    assert srcs["onchain"]["available"] is False               # clearly not fabricated
    assert out["by_month"][0]["month"] == THIS_MONTH


async def test_staking_income_none_stored_reports_unavailable(db):
    out = await mobile_analytics.staking_income_summary(3, 12, PRICES)
    assert out["total_usd"] == 0 and out["by_month"] == []
    assert out["available_from"] is None
    assert all(s["available"] is False for s in out["sources"])


def _client(monkeypatch):
    store = {}

    async def get_cache(key, user_id=None):
        return store.get((user_id, key))

    async def set_cache(key, value, ttl_seconds=300, user_id=None):
        store[(user_id, key)] = value

    async def prices():
        return PRICES

    monkeypatch.setattr(mobile, "get_cache", get_cache)
    monkeypatch.setattr(mobile, "set_cache", set_cache)
    monkeypatch.setattr(mobile.pricing_service, "get_all_tracked_prices", prices)
    app = FastAPI()
    app.include_router(mobile.router)
    app.dependency_overrides[verify_session] = lambda: 1
    return TestClient(app), store


def test_endpoints_return_data_are_cached_and_conditional(db, monkeypatch):
    client, store = _client(monkeypatch)
    for path in ("/api/mobile/analytics/fees?months=12", "/api/mobile/analytics/staking-income?months=12"):
        r = client.get(path)
        assert r.status_code == 200, r.text
        assert r.json()["months"] == 12
        etag = r.headers["etag"]
        # second call is served from the cache -> identical body -> 304 on conditional GET
        assert client.get(path).headers["etag"] == etag
        assert client.get(path, headers={"If-None-Match": etag}).status_code == 304
    assert client.get("/api/mobile/analytics/fees").json()["total_usd"] > 100
    assert "mobile_fees_v1_1_12" in {k[1] for k in store}


def test_months_is_bounded(db, monkeypatch):
    client, _ = _client(monkeypatch)
    assert client.get("/api/mobile/analytics/fees?months=0").status_code == 422
    assert client.get("/api/mobile/analytics/fees?months=61").status_code == 422
    assert client.get("/api/mobile/analytics/staking-income?months=61").status_code == 422
