"""
Server-fixes item 3 (2026-11-20): exchanges in all-holdings / wallet-breakdown.

- all-holdings reads every aggregation exchange (legacy + registry), not the
  hard-coded 7;
- a cold/expired `<name>_portfolio` cache no longer silently drops an
  exchange: stale rows are served flagged, cold ones are fetched bounded and
  reported as incomplete when they cannot be read;
- wallet-breakdown / wallet-sources exchange rows carry exchange_id and
  source_type 'exchange';
- ADA: staking-protocol positions and the wallet balance do not overlap.
"""

import asyncio
import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import routers.mobile as mobile  # noqa: E402
import routers.portfolio as portfolio_router  # noqa: E402
import services.exchange_holdings as eh  # noqa: E402

from tests.unit.test_btc_totals_integration import holdings_env  # noqa: E402,F401
from tests.unit.test_summary_cache_variants import (  # noqa: E402
    _install_fake_cache,
    _stub_metadata_cache,
)


@pytest.fixture(autouse=True)
def _reset_loader_state():
    eh._inflight.clear()
    eh._last_attempt.clear()
    yield
    eh._inflight.clear()
    eh._last_attempt.clear()


def _patch_cache(monkeypatch, fresh=None, stale=None):
    fresh = fresh or {}
    stale = stale or {}

    async def get_cache(key, user_id=None):
        return fresh.get(key)

    async def get_stale_cache(key, user_id=None):
        if key in stale:
            return stale[key], "2026-11-20T00:00:00"
        return None, None

    monkeypatch.setattr(eh, "get_cache", get_cache)
    monkeypatch.setattr(eh, "get_stale_cache", get_stale_cache)


# ------------------------------------------------------------------ loader

async def test_loader_covers_registry_exchanges(monkeypatch):
    from services.exchange_names import LEGACY_EXCHANGE_NAMES
    from routers.exchanges import EXCHANGE_REGISTRY
    registry_only = sorted(set(EXCHANGE_REGISTRY) - set(LEGACY_EXCHANGE_NAMES))
    assert registry_only
    _patch_cache(monkeypatch, fresh={f"{registry_only[0]}_portfolio": {"assets": [], "total_usd": 5}})

    async def never(user_id, name):
        raise AssertionError("fresh/none-configured path must not hit exchanges")

    async def not_configured(user_id, name):
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="nope")
    monkeypatch.setattr(eh, "_fetch_live", not_configured)

    loads = await eh.load_exchange_portfolios(1)
    by = {l["exchange_id"]: l for l in loads}
    assert registry_only[0] in by and by[registry_only[0]]["status"] == "fresh"
    assert len(loads) > len(LEGACY_EXCHANGE_NAMES)


async def test_stale_row_served_flagged_and_refresh_started(monkeypatch):
    _patch_cache(monkeypatch, stale={"bybit_portfolio": {"assets": [{"currency": "BTC"}], "total_usd": 9}})
    calls = []

    async def live(user_id, name):
        calls.append(name)
        return {"assets": [], "total_usd": 0}
    monkeypatch.setattr(eh, "_fetch_live", live)

    [load] = await eh.load_exchange_portfolios(1, names=["bybit"])
    assert load["status"] == "stale" and load["stale"] is True
    assert load["data"]["total_usd"] == 9            # served, not dropped
    await asyncio.sleep(0.01)
    assert calls == ["bybit"]                         # background warm started once


async def test_cold_exchange_is_fetched_live_within_timeout(monkeypatch):
    _patch_cache(monkeypatch)

    async def live(user_id, name):
        return {"assets": [{"currency": "ETH", "balance": 1}], "total_usd": 3000}
    monkeypatch.setattr(eh, "_fetch_live", live)

    [load] = await eh.load_exchange_portfolios(1, names=["kraken"])
    assert load["status"] == "live" and load["data"]["total_usd"] == 3000


async def test_cold_slow_exchange_is_warming_not_omitted_silently(monkeypatch):
    _patch_cache(monkeypatch)
    release = asyncio.Event()

    async def slow(user_id, name):
        await release.wait()
        return {"assets": [], "total_usd": 1}
    monkeypatch.setattr(eh, "_fetch_live", slow)

    [load] = await eh.load_exchange_portfolios(1, names=["kraken"], timeout=0.05)
    assert load["status"] == "warming" and load["data"] is None
    assert eh.incomplete([load]) == [load]
    release.set()
    await asyncio.sleep(0.01)


async def test_unconfigured_exchange_is_not_incomplete(monkeypatch):
    _patch_cache(monkeypatch)

    async def not_configured(user_id, name):
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="not configured")
    monkeypatch.setattr(eh, "_fetch_live", not_configured)

    [load] = await eh.load_exchange_portfolios(1, names=["bybit"])
    assert load["status"] == "not_configured"
    assert eh.incomplete([load]) == []


async def test_failed_exchange_is_unavailable_and_backs_off(monkeypatch):
    _patch_cache(monkeypatch)
    calls = []

    async def boom(user_id, name):
        calls.append(name)
        raise RuntimeError("upstream down")
    monkeypatch.setattr(eh, "_fetch_live", boom)

    [a] = await eh.load_exchange_portfolios(1, names=["bybit"])
    [b] = await eh.load_exchange_portfolios(1, names=["bybit"])
    assert a["status"] == "unavailable" and eh.incomplete([a])
    assert calls == ["bybit"]            # second request inside backoff: no new upstream call


async def test_no_live_mode_never_fetches(monkeypatch):
    _patch_cache(monkeypatch)

    async def boom(user_id, name):
        raise AssertionError("allow_live=False must not fetch")
    monkeypatch.setattr(eh, "_fetch_live", boom)
    [load] = await eh.load_exchange_portfolios(1, names=["bybit"], allow_live=False)
    assert load["data"] is None


# ---------------------------------------------------------- all-holdings

async def test_all_holdings_includes_registry_exchange_and_reports_state(holdings_env, monkeypatch):  # noqa: F811
    async def loads(user_id, names=None, allow_live=True, timeout=0):
        return [
            {"exchange_id": "bybit", "display_name": "Bybit", "stale": True, "status": "stale",
             "data": {"total_usd": 120.0, "assets": [
                 {"currency": "BTC", "balance": 0.002, "price": 60000.0, "name": "Bitcoin"}]}},
            {"exchange_id": "kraken", "display_name": "Kraken", "stale": False,
             "status": "warming", "data": None},
        ]
    import services.exchange_holdings as mod
    monkeypatch.setattr(mod, "load_exchange_portfolios", loads)

    result = await portfolio_router.get_all_holdings(user_id=1, refresh=True)
    btc = next(h for h in result["holdings"] if h["symbol"] == "BTC")
    assert btc["amount"] == pytest.approx(0.5 + 0.015 + 0.002)   # wallet + karma + bybit
    ex = {e["exchange_id"]: e for e in result["exchanges"]}
    assert ex["bybit"]["stale"] is True and ex["bybit"]["total_usd"] == 120.0
    assert ex["kraken"]["status"] == "warming"
    assert result["stale"] is True
    assert result["incomplete_sources"] == [{"exchange_id": "kraken", "status": "warming"}]


# ------------------------------------------------------- wallet-breakdown

async def test_wallet_breakdown_exchange_rows_have_exchange_id(monkeypatch):
    cache = _install_fake_cache(monkeypatch)
    _stub_metadata_cache(monkeypatch)

    async def prices():
        return {"ETH": {"usd": 3000.0}}
    monkeypatch.setattr(mobile.pricing_service, "get_all_tracked_prices", prices)

    async def loads(user_id, names=None, allow_live=True, timeout=0):
        return [
            {"exchange_id": "bybit", "display_name": "Bybit", "stale": True, "status": "stale",
             "data": {"assets": [{"currency": "ETH", "balance": 2.0}], "cached_at": "2026-11-20T01:00:00"}},
            {"exchange_id": "coinbase", "display_name": "Coinbase", "stale": False, "status": "fresh",
             "data": {"assets": [{"currency": "ETH", "balance": 1.0}]}},
            {"exchange_id": "kraken", "display_name": "Kraken", "stale": False, "status": "unavailable",
             "data": None},
        ]
    import services.exchange_holdings as mod
    monkeypatch.setattr(mod, "load_exchange_portfolios", loads)

    out = await mobile.get_asset_wallet_breakdown(symbol="eth", user_id=1)
    exch = {s["exchange_id"]: s for s in out["sources"] if s["source_type"] == "exchange"}
    assert set(exch) == {"bybit", "coinbase"}
    assert exch["bybit"]["stale"] is True and exch["coinbase"]["stale"] is False
    assert exch["bybit"]["label"] == "Bybit"
    assert out["stale"] is True
    assert out["incomplete_sources"] == [{"exchange_id": "kraken", "status": "unavailable"}]
    # incomplete results are cached only briefly
    assert "mobile_wallet_breakdown_v2_1_ETH" in cache.store


# ------------------------------------------------- ADA double-count audit

async def test_ada_staking_protocol_positions_do_not_overlap_wallet_balance(holdings_env, monkeypatch):  # noqa: F811
    """all-holdings ADA = wallet (L1) + protocol positions locked in
    contracts (Surf/Strike/Indigo CDP). Natively delegated ADA stays in the
    wallet balance and is NOT added again."""
    import routers.defi as defi_router

    async def summary(user_id=None, refresh=False):
        return {"cardano": {"total_ada": 1000.0, "wallet_count": 1}}
    monkeypatch.setattr(portfolio_router, "get_portfolio_summary", summary)

    ADDR = "addr1qtestada0000000000000000000000000000000000000000000000"

    async def wallets(user_id=None):
        return [{"address": ADDR, "blockchain": "cardano", "id": 1}]
    import database
    monkeypatch.setattr(database, "get_all_wallets", wallets)

    async def staking(address, refresh=False, user_id=None):
        return {"protocols": {"Surf Lending": {"staked": [{"token": "ADA", "amount": 200.0}]}}}
    monkeypatch.setattr(defi_router, "get_staking_positions", staking)

    from services.pricing import pricing_service

    async def prices():
        return {"ADA": {"usd": 0.5}, "BTC": {"usd": 60000.0}}
    monkeypatch.setattr(pricing_service, "get_all_tracked_prices", prices)

    result = await portfolio_router.get_all_holdings(user_id=1, refresh=True)
    ada = next(h for h in result["holdings"] if h["symbol"] == "ADA")
    assert ada["amount"] == pytest.approx(1000.0 + 200.0)
