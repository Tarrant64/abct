"""
Unit tests for ABCT-MOBILE-VALUE-MISMATCH-20260921 (symptom 2):

Overview's "All Holdings" / "Top Movers" (mobile /portfolio/summary
top_holdings) showed a per-chain's *display* value (native coin + native
CNT/token value) under the coin's own symbol bucket -- e.g. ADA's row
included the USD value of every other Cardano native token (IAG, STRIKE,
etc.) held in the wallet, while those same tokens ALSO appeared as their own
top_holdings rows a few lines later. That inflated "ADA" above its true
market value and double-counted the native tokens in the displayed list,
while /portfolio/all-holdings (the Assets tab) only ever valued the ADA row
at native_amount * market_price -- hence the two screens disagreeing on the
same ~41K ADA holding by the token's implied share of native-asset value.

The fix: top_holdings must use native_coin_value_usd (coin only) for each
symbol bucket; blockchain_summaries (the "blockchains" per-chain list) keeps
the combined display value, which is unaffected here and separately
regression-guarded below.
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

from tests.unit.test_summary_cache_variants import (  # noqa: E402
    _install_fake_cache,
    _stub_compute_upstreams,
)

USER_ID = 9090

# A Cardano wallet holding 1,000 ADA (@ $0.24 = $240) plus $60 of other
# native CNTs (already reflected in native_assets_value_usd, as
# get_portfolio_summary's per-chain aggregation produces it) -- the
# per-chain *display* value is therefore $300, a 1.25x inflation ratio if
# the bug is present, in the same ballpark as the ~1.2x the user reported.
# get_all_native_assets (the per-token merge step that would otherwise
# individually re-add those CNTs to top_holdings) is stubbed to return
# nothing, isolating this test to the blockchain_summaries -> symbol_agg
# seeding bug rather than the token-merge step (which calls out to
# metadata_cache/CoinGecko for name/image resolution).
ADA_QTY = 1000.0
ADA_PRICE = 0.24
NATIVE_TOKENS_VALUE = 60.0


async def _run_summary(monkeypatch):
    _install_fake_cache(monkeypatch)
    _stub_compute_upstreams(monkeypatch)

    async def get_portfolio_summary(user_id, refresh):
        return {
            "cardano": {
                "wallet_count": 1,
                "total_ada": ADA_QTY,
                "native_assets_value_usd": NATIVE_TOKENS_VALUE,
            }
        }

    async def get_all_tracked_prices():
        return {"ADA": {"usd": ADA_PRICE, "usd_24h_change": 0}}

    monkeypatch.setattr(mobile.portfolio, "get_portfolio_summary", get_portfolio_summary)
    monkeypatch.setattr(mobile.pricing_service, "get_all_tracked_prices", get_all_tracked_prices)

    return await mobile.get_mobile_portfolio_summary(
        user_id=USER_ID, refresh=False, include_sparklines=False)


async def test_top_holdings_ada_value_excludes_other_native_tokens(monkeypatch):
    result = await _run_summary(monkeypatch)

    top_holdings = {h["symbol"]: h for h in result["top_holdings"]}
    assert "ADA" in top_holdings
    # Coin-only value ($240), NOT the per-chain display value ($300) that
    # bundles in the $60 of other native tokens.
    assert top_holdings["ADA"]["value_usd"] == pytest.approx(
        ADA_QTY * ADA_PRICE, abs=0.01)


async def test_blockchains_list_keeps_combined_display_value(monkeypatch):
    """Regression guard: the per-chain "blockchains" card is intentionally
    unaffected by this fix -- it's meant to show everything held on that
    chain, coin + native tokens together."""
    result = await _run_summary(monkeypatch)

    blockchains = {b["symbol"]: b for b in result["blockchains"]}
    assert blockchains["ADA"]["value_usd"] == pytest.approx(
        ADA_QTY * ADA_PRICE + NATIVE_TOKENS_VALUE, abs=0.01)
    assert blockchains["ADA"]["native_coin_value_usd"] == pytest.approx(
        ADA_QTY * ADA_PRICE, abs=0.01)
