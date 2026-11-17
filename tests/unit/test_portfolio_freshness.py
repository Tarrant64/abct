"""
Unit tests for ABCT-ASSET-FRESHNESS-20261117.

Editing a manual stock / custom token / wallet used to leave the main
dashboard showing the OLD quantity after a reload, because the server-side
derived caches (portfolio summary/totals/all-holdings/...) and the
portfolio_positions snapshot were never invalidated by the edit endpoints.

Covers: invalidation helper (real throwaway cache table), the decorator,
stock write endpoints, the per-item refresh endpoints (incl. ownership),
the stale-snapshot fix in /portfolio/instant, and the version token.
No network, TEST-NET addresses only.
"""

import os
import sqlite3
import sys

import pytest
from fastapi import HTTPException

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402
from services import portfolio_freshness as pf  # noqa: E402

SCHEMA = """
CREATE TABLE users (id INTEGER PRIMARY KEY);
CREATE TABLE cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE(user_id, key),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE portfolio_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, symbol TEXT,
    quantity REAL, source_type TEXT, source_detail TEXT, chain TEXT,
    last_price_usd REAL
);
INSERT INTO users (id) VALUES (1);
INSERT INTO users (id) VALUES (2);
"""

USER_KEYS = [
    "portfolio_summary_{u}", "portfolio_totals_{u}", "portfolio_instant_{u}",
    "portfolio_analytics_{u}", "all_holdings_v2_{u}", "all_holdings_v2_{u}_all",
    "unified_chart_v2_{u}_1w", "unified_chart_v2_{u}_1w_by_chain",
    "portfolio_24h_hourly_v2_{u}", "asset_breakdown_cardano_{u}",
    "price_chart_v2_cardano_1w_{u}", "mobile_portfolio_summary_v2_{u}_full",
    "wallet_balance_7",
]


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "fresh.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    monkeypatch.setattr(database, "DATABASE_PATH", str(path))
    return path


def _keys(path, user_id):
    conn = sqlite3.connect(path)
    rows = conn.execute("SELECT key FROM cache WHERE user_id = ?", (user_id,)).fetchall()
    conn.close()
    return {r[0] for r in rows}


async def _seed(user_id):
    for k in USER_KEYS:
        await database.set_cache(k.format(u=user_id), {"stale": True}, 3600, user_id=user_id)


async def test_invalidate_clears_all_derived_caches_for_user_only(db_path):
    await _seed(1)
    await _seed(2)
    await pf.invalidate_user_portfolio_caches(1, "test")
    left = _keys(db_path, 1)
    # Only the version token survives for the edited user (wallet_balance_7
    # is untouched unless wallet_ids is passed).
    assert left == {"portfolio_version_1", "wallet_balance_7"}
    assert len(_keys(db_path, 2)) == len(USER_KEYS)  # other user untouched


async def test_invalidate_wallet_ids_clears_wallet_balance_cache(db_path):
    await _seed(1)
    await pf.invalidate_user_portfolio_caches(1, "t", wallet_ids=[7])
    assert "wallet_balance_7" not in _keys(db_path, 1)


async def test_clear_stock_positions_only_removes_stock_rows(db_path):
    conn = sqlite3.connect(db_path)
    conn.executemany(
        "INSERT INTO portfolio_positions (user_id, symbol, quantity, source_type) VALUES (?,?,?,?)",
        [(1, "BITW", 5, "manual_stock"), (1, "ADA", 10, "chain"), (2, "BITW", 9, "manual_stock")])
    conn.commit()
    conn.close()
    await pf.invalidate_user_portfolio_caches(1, "t", clear_stock_positions=True)
    conn = sqlite3.connect(db_path)
    rows = set(conn.execute("SELECT user_id, symbol FROM portfolio_positions").fetchall())
    conn.close()
    assert rows == {(1, "ADA"), (2, "BITW")}


async def test_version_changes_on_every_invalidation(db_path):
    assert await pf.get_portfolio_version(1) == "0"
    v1 = await pf.invalidate_user_portfolio_caches(1, "a")
    assert await pf.get_portfolio_version(1) == v1
    v2 = await pf.invalidate_user_portfolio_caches(1, "b")
    assert v2 != v1 and await pf.get_portfolio_version(1) == v2
    assert await pf.get_portfolio_version(2) == "0"


async def test_decorator_invalidates_only_after_success(monkeypatch):
    calls = []

    async def fake_inv(uid, reason, **kw):
        calls.append((uid, reason, kw))
        return "v"
    monkeypatch.setattr(pf, "invalidate_user_portfolio_caches", fake_inv)

    @pf.invalidates_portfolio("edit", clear_stock_positions=True)
    async def ok(x, user_id=None):
        return {"x": x}

    @pf.invalidates_portfolio("edit")
    async def boom(user_id=None):
        raise HTTPException(status_code=404, detail="nope")

    assert await ok(3, user_id=5) == {"x": 3}
    assert calls == [(5, "edit", {"clear_stock_positions": True})]
    with pytest.raises(HTTPException):
        await boom(user_id=5)
    assert len(calls) == 1  # failed edit did not churn caches


def test_write_endpoints_are_decorated():
    """Every stock/custom-token/wallet write endpoint carries the decorator
    (functools.wraps exposes the original through __wrapped__)."""
    from routers import stocks, custom_tokens, wallets
    for fn in (stocks.add_stock, stocks.update_stock, stocks.delete_stock,
               custom_tokens.add_token, custom_tokens.update_token,
               custom_tokens.remove_token, custom_tokens.toggle_token_inclusion,
               wallets.add_wallet, wallets.add_multiple_wallets,
               wallets.add_xpub_addresses, wallets.delete_stake_group,
               wallets.update_wallet, wallets.delete_wallet,
               wallets.toggle_asset_ignore):
        assert hasattr(fn, "__wrapped__"), fn.__name__


async def test_update_stock_invalidates_caches(monkeypatch):
    from routers import stocks
    row = {"id": 4, "symbol": "BITW", "quantity": 10, "user_id": 1}
    state = {"row": row}

    async def get_row(sid, uid):
        return state["row"] if sid == 4 and uid == 1 else None

    async def upd(sid, updates, uid):
        state["row"] = {**state["row"], **updates}

    async def quotes(symbols, use_cache=True):
        return {}
    calls = []

    async def fake_inv(uid, reason, **kw):
        calls.append((uid, kw))
        return "v"
    monkeypatch.setattr(stocks, "get_manual_stock_by_id", get_row)
    monkeypatch.setattr(stocks, "update_manual_stock", upd)
    monkeypatch.setattr(stocks.stock_data_service, "get_quotes", quotes)
    monkeypatch.setattr(pf, "invalidate_user_portfolio_caches", fake_inv)

    req = stocks.StockUpdateRequest(quantity=25)
    out = await stocks.update_stock(4, req, user_id=1)
    assert out["stock"]["quantity"] == 25
    assert calls == [(1, {"clear_stock_positions": True})]

    with pytest.raises(HTTPException):
        await stocks.update_stock(4, req, user_id=2)  # not theirs
    assert len(calls) == 1


async def test_refresh_stock_updates_price_and_invalidates(monkeypatch):
    from routers import stocks
    state = {"row": {"id": 4, "symbol": "BITW", "quantity": 3, "price_usd": 10.0}}

    async def get_row(sid, uid):
        return state["row"] if sid == 4 and uid == 1 else None

    async def upd(sid, updates, uid):
        u = dict(updates)
        u.pop("last_price_update", None)
        state["row"] = {**state["row"], **u}

    async def quotes(symbols, use_cache=True):
        assert use_cache is False  # per-item refresh must bypass the quote cache
        return {"BITW": {"price_usd": 12.5, "prev_close_usd": 12.0, "change_pct": 4.1,
                         "source": "test"}}
    calls = []

    async def fake_inv(uid, reason, **kw):
        calls.append((uid, kw))
        return "ver1"
    monkeypatch.setattr(stocks, "get_manual_stock_by_id", get_row)
    monkeypatch.setattr(stocks, "update_manual_stock", upd)
    monkeypatch.setattr(stocks.stock_data_service, "get_quotes", quotes)
    monkeypatch.setattr(pf, "invalidate_user_portfolio_caches", fake_inv)

    out = await stocks.refresh_stock(4, user_id=1)
    assert out["price_refreshed"] is True
    assert out["stock"]["price_usd"] == 12.5 and out["stock"]["value_usd"] == 37.5
    assert out["portfolio_version"] == "ver1"
    assert calls == [(1, {"clear_stock_positions": True})]

    with pytest.raises(HTTPException) as ei:
        await stocks.refresh_stock(4, user_id=2)
    assert ei.value.status_code == 404


async def test_refresh_stock_keeps_price_when_unquotable(monkeypatch):
    from routers import stocks
    state = {"row": {"id": 4, "symbol": "BITW", "quantity": 3, "price_usd": 10.0}}

    async def get_row(sid, uid):
        return state["row"]

    async def upd(*a, **k):
        raise AssertionError("must not overwrite price without a quote")

    async def quotes(symbols, use_cache=True):
        return {}

    async def fake_inv(uid, reason, **kw):
        return "v"
    monkeypatch.setattr(stocks, "get_manual_stock_by_id", get_row)
    monkeypatch.setattr(stocks, "update_manual_stock", upd)
    monkeypatch.setattr(stocks.stock_data_service, "get_quotes", quotes)
    monkeypatch.setattr(pf, "invalidate_user_portfolio_caches", fake_inv)
    out = await stocks.refresh_stock(4, user_id=1)
    assert out["price_refreshed"] is False and out["stock"]["price_usd"] == 10.0


async def test_refresh_wallet_requires_ownership_and_invalidates(monkeypatch):
    from routers import wallets
    wallet = {"id": 7, "address": "addr_test_192.0.2.1", "blockchain": "bitcoin", "user_id": 1}

    async def get_w(address, blockchain=None, user_id=None):
        return wallet if user_id == 1 else None

    async def fake_refresh(w):
        return {"address": w["address"], "success": True}
    calls = []

    async def fake_inv(uid, reason, **kw):
        calls.append((uid, kw))
        return "wv"
    monkeypatch.setattr(wallets, "get_wallet_by_address", get_w)
    monkeypatch.setattr(wallets, "_refresh_wallet_balance", fake_refresh)
    monkeypatch.setattr(pf, "invalidate_user_portfolio_caches", fake_inv)

    out = await wallets.refresh_wallet_balance("addr_test_192.0.2.1", user_id=1)
    assert out["success"] and out["portfolio_version"] == "wv"
    assert calls == [(1, {"wallet_ids": [7]})]
    with pytest.raises(HTTPException) as ei:
        await wallets.refresh_wallet_balance("addr_test_192.0.2.1", user_id=2)
    assert ei.value.status_code == 404
    assert len(calls) == 1


async def test_refresh_custom_token_ownership_and_invalidation(monkeypatch):
    from routers import custom_tokens as ct
    tok = {"id": 3, "ticker": "TST", "quantity": 1}

    async def get_t(tid, user_id=None):
        return tok if (tid == 3 and user_id == 1) else None
    calls = []

    async def fake_inv(uid, reason, **kw):
        calls.append(uid)
        return "tv"
    monkeypatch.setattr(ct, "get_custom_token_by_id", get_t)
    monkeypatch.setattr(pf, "invalidate_user_portfolio_caches", fake_inv)
    out = await ct.refresh_token(3, user_id=1)
    assert out["status"] == "success" and out["portfolio_version"] == "tv"
    with pytest.raises(HTTPException):
        await ct.refresh_token(3, user_id=2)
    assert calls == [1]


async def test_instant_ignores_stale_manual_stock_snapshot(monkeypatch):
    """The BITW bug: portfolio_positions still held the OLD quantity (only a
    full summary rewrites it) and masked the edited manual_stocks row."""
    from routers import portfolio
    import database as dbm

    async def positions(uid):
        return [{"symbol": "BITW", "quantity": 100.0, "source_type": "manual_stock",
                 "last_price_usd": 10.0, "chain": ""}]

    async def fresh(uid):
        return {}

    async def stocks_rows(user_id=None):
        return [{"id": 1, "symbol": "BITW", "quantity": 250.0, "price_usd": 10.0,
                 "include_in_total": 1, "change_pct": 0}]

    async def prices():
        return {}

    async def nft_pref(uid):
        return False
    monkeypatch.setattr(dbm, "get_all_portfolio_positions", positions)
    monkeypatch.setattr(dbm, "get_positions_freshness", fresh)
    monkeypatch.setattr(dbm, "get_all_manual_stocks", stocks_rows)
    monkeypatch.setattr(portfolio.pricing_service, "get_all_tracked_prices", prices)
    monkeypatch.setattr(portfolio, "get_nft_inclusion_preference", nft_pref)

    out = await portfolio.get_portfolio_instant(user_id=1)
    assert out["total_usd"] == 2500.0  # 250 x 10, not the stale 100 x 10
    assert out["breakdown"]["manual_stock"] == 2500.0


async def test_version_endpoint(db_path):
    from routers import portfolio
    assert (await portfolio.get_portfolio_version_token(user_id=1)) == {"version": "0"}
    v = await pf.invalidate_user_portfolio_caches(1, "x")
    assert (await portfolio.get_portfolio_version_token(user_id=1)) == {"version": v}
