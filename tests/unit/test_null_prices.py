"""
Server-fixes item 1 (2026-11-20): unknown prices are null, never 0.

An unknown `price_usd` / `price_change_24h` used to be emitted as 0, which the
apps rendered as a fake "$0.00" / "0.00%". They are now null so clients can
show "—". USD *values* stay numeric (0 when unvalued); only the reported
price fields change. A genuine 0% change is still 0.0, not null.
"""

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

from tests.unit.test_btc_totals_integration import holdings_env  # noqa: E402,F401
from tests.unit.test_summary_cache_variants import (  # noqa: E402
    _install_fake_cache,
    _stub_compute_upstreams,
)


def test_known_price_helpers():
    kp, kc = portfolio_router._known_price, portfolio_router._known_change
    assert kp({"usd": 1.5}) == 1.5
    assert kp({"usd": 0}) is None
    assert kp({"usd": None}) is None
    assert kp({}) is None
    assert kp(None) is None
    assert kc({"usd_24h_change": 0}) == 0.0          # real 0% is NOT unknown
    assert kc({"usd_24h_change": -3.2}) == -3.2
    assert kc({"usd_24h_change": None}) is None
    assert kc({}) is None


async def test_all_holdings_unpriced_chain_and_token_are_null(holdings_env, monkeypatch):  # noqa: F811
    async def fake_assets(user_id=None, refresh=False):
        return {
            "valuable_assets": [],
            "assets": [{"ticker": "MYSTERY", "asset_name": "Mystery", "total_quantity": 5.0,
                        "wallet_count": 1}],
        }
    monkeypatch.setattr(portfolio_router, "get_all_native_assets", fake_assets)

    result = await portfolio_router.get_all_holdings(user_id=1, refresh=True, include_all=True)
    rows = {h["symbol"]: h for h in result["holdings"]}

    btc = rows["BTC"]                       # priced, no 24h change in feed
    assert btc["price_usd"] == 60000.0
    assert btc["price_change_24h"] is None
    mystery = rows["MYSTERY"]               # no price at all
    assert mystery["price_usd"] is None
    assert mystery["price_change_24h"] is None
    assert mystery["value_usd"] == 0        # values stay numeric


async def test_all_holdings_real_zero_change_stays_zero(holdings_env, monkeypatch):  # noqa: F811
    from services.pricing import pricing_service

    async def fake_prices():
        return {"BTC": {"usd": 60000.0, "usd_24h_change": 0}}
    monkeypatch.setattr(pricing_service, "get_all_tracked_prices", fake_prices)
    result = await portfolio_router.get_all_holdings(user_id=1, refresh=True)
    btc = next(h for h in result["holdings"] if h["symbol"] == "BTC")
    assert btc["price_change_24h"] == 0.0


async def test_merge_into_unpriced_row_adopts_later_price():
    holdings = {"FOO": {"symbol": "FOO", "amount": 1.0, "price_usd": None,
                        "value_usd": 0, "logo_url": ""}}
    portfolio_router._merge_holding(holdings, "FOO", 2.0, 0.0,
                                    {"FOO": {"usd": 3.0}}, source="staking")
    assert holdings["FOO"]["price_usd"] == 3.0
    assert holdings["FOO"]["value_usd"] == pytest.approx(9.0)


async def test_mobile_summary_unpriced_chain_is_null(monkeypatch):
    _install_fake_cache(monkeypatch)
    _stub_compute_upstreams(monkeypatch)

    async def get_portfolio_summary(user_id, refresh):
        return {"cardano": {"wallet_count": 1, "total_ada": 100.0,
                            "native_assets_value_usd": 5.0}}

    async def get_all_tracked_prices():
        return {}   # price feed has no ADA

    monkeypatch.setattr(mobile.portfolio, "get_portfolio_summary", get_portfolio_summary)
    monkeypatch.setattr(mobile.pricing_service, "get_all_tracked_prices", get_all_tracked_prices)
    result = await mobile.get_mobile_portfolio_summary(
        user_id=1, refresh=False, include_sparklines=False)

    ada = next(b for b in result["blockchains"] if b["symbol"] == "ADA")
    assert ada["native_price_usd"] is None
    assert ada["price_change_24h"] is None
    top = {h["symbol"]: h for h in result["top_holdings"]}
    assert top["ADA"]["native_price_usd"] is None
    assert top["ADA-OTHER"]["native_price_usd"] is None
    assert top["ADA-OTHER"]["price_change_24h"] is None
