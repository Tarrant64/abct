"""
ABCT-POLISH-20261121 items 2 + 3.

2. GET /api/mobile/exchanges/{name} answered 404 for every registry exchange (only the 7 legacy ones were
   mapped). It now resolves every id from get_aggregation_exchange_names(), and the summary exposes an
   additive `exchange_id` that the detail route accepts.
3. wallet-breakdown staking covered Cardano only; BTC Karma stakes on Bitcoin wallets are now included via
   the same iter_staking_token_values valuation, once per address, without touching the L1 wallet row.
"""
import os
import sys

import pytest
from fastapi import HTTPException

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import routers.exchanges as exchanges_router  # noqa: E402
import routers.mobile as mobile  # noqa: E402
import services.exchange_holdings as eh  # noqa: E402
from services.exchange_names import get_aggregation_exchange_names  # noqa: E402

from tests.unit.test_summary_cache_variants import (  # noqa: E402
    FakeCacheStore,
    _install_fake_cache,
    _stub_metadata_cache,
)


# ------------------------------------------------------------ item 2

def test_every_aggregation_exchange_resolves():
    names = get_aggregation_exchange_names()
    assert len(names) > 7
    for n in names:
        assert mobile._resolve_exchange_id(n) == n
        assert mobile._resolve_exchange_id(n.upper()) == n


def test_label_derived_aliases_resolve_to_registry_ids():
    # the summary has always emitted display-label derived names
    assert mobile._resolve_exchange_id("woo_x") == "woox"
    assert mobile._resolve_exchange_id("crypto_com") == "cryptocom"
    assert mobile._resolve_exchange_id("independent_reserve") == "independentreserve"
    assert mobile._resolve_exchange_id("xt_com") == "xt"
    assert mobile._resolve_exchange_id("binance_us") == "binance_us"


@pytest.mark.parametrize("bad", ["", "  ", "nope", "../etc", "kraken/../x", "%00"])
def test_unknown_names_do_not_resolve(bad):
    assert mobile._resolve_exchange_id(bad) is None


async def test_detail_404_for_unknown_exchange():
    with pytest.raises(HTTPException) as e:
        await mobile.get_mobile_exchange_detail(exchange_name="nonexistent", user_id=1, refresh=False)
    assert e.value.status_code == 404


async def test_detail_works_for_every_exchange(monkeypatch):
    seen = []

    async def fake_fetch(name, user_id, refresh=False):
        seen.append(name)
        return {"configured": True, "total_usd": 12.345, "from_cache": True,
                "assets": [{"currency": "BTC", "balance": 0.001, "usd_value": 12.345, "price": 12345.0}]}
    monkeypatch.setattr(exchanges_router, "fetch_exchange_portfolio", fake_fetch)

    for name in get_aggregation_exchange_names():
        out = await mobile.get_mobile_exchange_detail(exchange_name=name, user_id=1, refresh=False)
        assert out["exchange"] == name
        assert out["display_name"]
        assert out["total_usd"] == 12.35 and out["asset_count"] == 1
        assert out["assets"][0]["symbol"] == "BTC"
    assert seen == get_aggregation_exchange_names()


async def test_detail_alias_is_canonicalised_and_503_passes_through(monkeypatch):
    called = []

    async def fake_fetch(name, user_id, refresh=False):
        called.append(name)
        raise HTTPException(status_code=503, detail="Kraken API not configured")
    monkeypatch.setattr(exchanges_router, "fetch_exchange_portfolio", fake_fetch)
    with pytest.raises(HTTPException) as e:
        await mobile.get_mobile_exchange_detail(exchange_name="woo_x", user_id=1, refresh=False)
    assert e.value.status_code == 503 and called == ["woox"]


async def test_detail_unexpected_error_is_500_without_leak(monkeypatch):
    async def boom(name, user_id, refresh=False):
        raise RuntimeError("secret internals")
    monkeypatch.setattr(exchanges_router, "fetch_exchange_portfolio", boom)
    with pytest.raises(HTTPException) as e:
        await mobile.get_mobile_exchange_detail(exchange_name="kraken", user_id=1, refresh=False)
    assert e.value.status_code == 500 and "secret" not in e.value.detail


async def test_summary_adds_exchange_id_additively(monkeypatch):
    async def summary(user_id=None):
        return {"total_usd": 5, "exchanges": [
            {"name": "WOO X", "total_usd": 3, "asset_count": 1, "status": "connected"},
            {"name": "Kraken", "total_usd": 2, "asset_count": 1, "status": "connected"}]}
    monkeypatch.setattr(exchanges_router, "get_all_exchanges_summary", summary)
    out = await mobile.get_mobile_exchanges_summary(user_id=1, refresh=False)
    by = {e["name"]: e for e in out["exchanges"]}
    assert by["woo_x"]["exchange_id"] == "woox"          # `name` unchanged, new field usable on the detail route
    assert by["kraken"]["exchange_id"] == "kraken"
    assert {"name", "display_name", "configured", "value_usd", "asset_count", "logo_url", "last_sync"} <= set(by["kraken"])


# ------------------------------------------------------------ item 3

BTC_ADDR = "bc1qtestaddress0000000000000000000000000"
ADA_ADDR = "addr1qtestada"
KARMA = {"protocols": {"BTC Karma": {
    "staked": [{"token": "BTC", "amount": 0.015, "positions": 1}],
    "status": "ok"}}}


def _breakdown_env(monkeypatch, karma_for=None, extra_btc_wallets=()):
    cache = _install_fake_cache(monkeypatch)
    _stub_metadata_cache(monkeypatch)
    wallets = [{"address": BTC_ADDR, "label": "Cold", "balance": 0.5}] + list(extra_btc_wallets)
    cache.seed("portfolio_summary_1", {
        "bitcoin": {"wallets": wallets},
        "cardano": {"wallets": [{"address": ADA_ADDR, "label": "Ada", "balance": 100}]},
    })
    cache.seed("native_assets_all", {})
    for addr in (karma_for or []):
        cache.seed(f"btc_karma_staking_{addr}", KARMA)

    async def prices():
        return {"BTC": {"usd": 60000.0}, "ADA": {"usd": 0.5}}
    monkeypatch.setattr(mobile.pricing_service, "get_all_tracked_prices", prices)

    async def loads(user_id, names=None, allow_live=True, timeout=0):
        return []
    monkeypatch.setattr(eh, "load_exchange_portfolios", loads)

    async def no_defi(key, user_id=None):
        return None
    return cache


async def test_breakdown_includes_btc_karma_staking(monkeypatch):
    _breakdown_env(monkeypatch, karma_for=[BTC_ADDR])
    out = await mobile.get_asset_wallet_breakdown(symbol="btc", user_id=1)
    kinds = {s["source_type"]: s for s in out["sources"]}
    assert kinds["wallet"]["amount"] == 0.5
    st = kinds["staking"]
    assert st["blockchain"] == "bitcoin" and st["address"] == BTC_ADDR
    assert st["amount"] == 0.015 and st["value_usd"] == 900.0
    assert "BTC Karma" in st["label"]
    # no double count: wallet 0.5 + staked 0.015, wallet row not inflated
    assert out["total_amount"] == pytest.approx(0.515)
    assert out["total_value_usd"] == pytest.approx(0.515 * 60000)


async def test_breakdown_btc_without_karma_is_unchanged(monkeypatch):
    _breakdown_env(monkeypatch)
    out = await mobile.get_asset_wallet_breakdown(symbol="btc", user_id=1)
    assert [s["source_type"] for s in out["sources"]] == ["wallet"]
    assert out["total_amount"] == 0.5


async def test_breakdown_dedupes_wallets_sharing_an_address(monkeypatch):
    dup = {"address": BTC_ADDR, "label": "Dup", "balance": 0.1}
    _breakdown_env(monkeypatch, karma_for=[BTC_ADDR], extra_btc_wallets=[dup])
    out = await mobile.get_asset_wallet_breakdown(symbol="btc", user_id=1)
    staking = [s for s in out["sources"] if s["source_type"] == "staking"]
    assert len(staking) == 1


async def test_breakdown_ignores_unavailable_karma_and_other_symbols(monkeypatch):
    cache = _breakdown_env(monkeypatch)
    cache.seed(f"btc_karma_staking_{BTC_ADDR}", {"protocols": {"BTC Karma": {
        "status": "unavailable", "staked": [{"token": "BTC", "amount": 9.0}]}}})
    out = await mobile.get_asset_wallet_breakdown(symbol="btc", user_id=1)
    assert [s["source_type"] for s in out["sources"]] == ["wallet"]
    # ADA breakdown must not pick up BTC stakes
    cache2 = _breakdown_env(monkeypatch, karma_for=[BTC_ADDR])
    ada = await mobile.get_asset_wallet_breakdown(symbol="ada", user_id=1)
    assert all(s.get("blockchain") != "bitcoin" for s in ada["sources"])
