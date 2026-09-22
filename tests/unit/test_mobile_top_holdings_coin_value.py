"""
Unit tests for ABCT-MOBILE-VALUE-MISMATCH-20260921 (symptom 2) and its
follow-up ABCT-MOBILE-VALUE-MISMATCH-20260921-B (review gap 1):

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

-B closes the gap that first fix opened: native_tokens_value_usd (from
calculate_wallet_native_assets_value, per chain) and the top_holdings
token-merge step's source (get_all_native_assets — an INDEPENDENT
valuation) are not guaranteed to agree token-for-token, for any chain. If a
chain's declared native_tokens_value isn't fully itemized by the merge step,
the remainder now gets one explicit "<COIN>-OTHER" placeholder row instead
of silently vanishing -- covered by the non-Cardano-chain tests below.
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

    # ABCT-MOBILE-VALUE-MISMATCH-20260921-B: get_all_native_assets is
    # stubbed (via _stub_compute_upstreams) to return no valuable_assets, so
    # none of the $60 of declared native_tokens_value_usd gets itemized by
    # the token-merge step. Without the reconciliation fix that $60 would
    # simply vanish from top_holdings; with it, a placeholder row makes up
    # the shortfall so coin ($240) + placeholder ($60) == the full $300
    # blockchain-card value, with the coin row itself never re-inflated.
    assert "ADA-OTHER" in top_holdings
    assert top_holdings["ADA-OTHER"]["value_usd"] == pytest.approx(
        NATIVE_TOKENS_VALUE, abs=0.01)
    assert top_holdings["ADA"]["value_usd"] + top_holdings["ADA-OTHER"]["value_usd"] == pytest.approx(
        ADA_QTY * ADA_PRICE + NATIVE_TOKENS_VALUE, abs=0.01)


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


# ---------------------------------------------------------------------------
# ABCT-MOBILE-VALUE-MISMATCH-20260921-B: non-Cardano chains, gap 1
# ---------------------------------------------------------------------------

ETH_QTY = 2.0
ETH_PRICE = 2000.0
ETH_NATIVE_TOKENS_VALUE = 100.0  # one ERC-20 (USDT), fully itemized below

SOL_QTY = 10.0
SOL_PRICE = 150.0
SOL_NATIVE_TOKENS_VALUE = 80.0  # two SPL tokens' worth; only one is itemized


async def _run_multichain_summary(monkeypatch, native_assets):
    _install_fake_cache(monkeypatch)
    _stub_compute_upstreams(monkeypatch)

    async def get_portfolio_summary(user_id, refresh):
        return {
            "ethereum": {
                "wallet_count": 1,
                "total_eth": ETH_QTY,
                "native_assets_value_usd": ETH_NATIVE_TOKENS_VALUE,
            },
            "solana": {
                "wallet_count": 1,
                "total_sol": SOL_QTY,
                "native_assets_value_usd": SOL_NATIVE_TOKENS_VALUE,
            },
        }

    async def get_all_tracked_prices():
        return {
            "ETH": {"usd": ETH_PRICE, "usd_24h_change": 0},
            "SOL": {"usd": SOL_PRICE, "usd_24h_change": 0},
        }

    async def get_all_native_assets(user_id):
        return {"valuable_assets": native_assets}

    async def resolve_token_info(symbol):
        return (symbol, "")

    monkeypatch.setattr(mobile.portfolio, "get_portfolio_summary", get_portfolio_summary)
    monkeypatch.setattr(mobile.pricing_service, "get_all_tracked_prices", get_all_tracked_prices)
    monkeypatch.setattr(mobile.portfolio, "get_all_native_assets", get_all_native_assets)
    monkeypatch.setattr(mobile, "_resolve_token_info", resolve_token_info)

    return await mobile.get_mobile_portfolio_summary(
        user_id=USER_ID, refresh=False, include_sparklines=False)


async def test_non_cardano_chain_fully_itemized_gets_no_placeholder(monkeypatch):
    """Ethereum's $100 of native_tokens_value_usd is fully covered by one
    itemized USDT row -- no ETH-OTHER placeholder, no double count."""
    native_assets = [{
        "ticker": "USDT", "asset_name": "Tether", "blockchain": "ethereum",
        "total_quantity": 100.0, "value_usd": ETH_NATIVE_TOKENS_VALUE,
        "wallet_count": 1,
    }]
    result = await _run_multichain_summary(monkeypatch, native_assets)

    top_holdings = {h["symbol"]: h for h in result["top_holdings"]}
    assert top_holdings["ETH"]["value_usd"] == pytest.approx(ETH_QTY * ETH_PRICE, abs=0.01)
    assert top_holdings["USDT"]["value_usd"] == pytest.approx(ETH_NATIVE_TOKENS_VALUE, abs=0.01)
    assert "ETH-OTHER" not in top_holdings

    chain_total = top_holdings["ETH"]["value_usd"] + top_holdings["USDT"]["value_usd"]
    assert chain_total == pytest.approx(ETH_QTY * ETH_PRICE + ETH_NATIVE_TOKENS_VALUE, abs=0.01)


async def test_non_cardano_chain_partially_itemized_adds_placeholder_for_remainder(monkeypatch):
    """Solana's $80 of native_tokens_value_usd is only half-covered by the
    one itemized USDC row ($50) -- the other $30 (a second SPL token the
    merge step didn't itemize, e.g. no ticker match) gets a SOL-OTHER
    placeholder instead of silently disappearing, and USDC is not
    double-counted inside it."""
    native_assets = [{
        "ticker": "USDC", "asset_name": "USD Coin", "blockchain": "solana",
        "total_quantity": 50.0, "value_usd": 50.0,
        "wallet_count": 1,
    }]
    result = await _run_multichain_summary(monkeypatch, native_assets)

    top_holdings = {h["symbol"]: h for h in result["top_holdings"]}
    assert top_holdings["SOL"]["value_usd"] == pytest.approx(SOL_QTY * SOL_PRICE, abs=0.01)
    assert top_holdings["USDC"]["value_usd"] == pytest.approx(50.0, abs=0.01)
    assert "SOL-OTHER" in top_holdings
    assert top_holdings["SOL-OTHER"]["value_usd"] == pytest.approx(30.0, abs=0.01)

    chain_total = (
        top_holdings["SOL"]["value_usd"]
        + top_holdings["USDC"]["value_usd"]
        + top_holdings["SOL-OTHER"]["value_usd"]
    )
    assert chain_total == pytest.approx(SOL_QTY * SOL_PRICE + SOL_NATIVE_TOKENS_VALUE, abs=0.01)


async def test_two_chains_together_no_cross_chain_leakage(monkeypatch):
    """Sanity check: ETH's fully-itemized token and SOL's shortfall
    placeholder don't interfere with each other -- each chain's
    reconciliation is independent."""
    native_assets = [
        {"ticker": "USDT", "asset_name": "Tether", "blockchain": "ethereum",
         "total_quantity": 100.0, "value_usd": ETH_NATIVE_TOKENS_VALUE, "wallet_count": 1},
        {"ticker": "USDC", "asset_name": "USD Coin", "blockchain": "solana",
         "total_quantity": 50.0, "value_usd": 50.0, "wallet_count": 1},
    ]
    result = await _run_multichain_summary(monkeypatch, native_assets)

    top_holdings = {h["symbol"]: h for h in result["top_holdings"]}
    assert "ETH-OTHER" not in top_holdings
    assert "SOL-OTHER" in top_holdings
    assert top_holdings["SOL-OTHER"]["value_usd"] == pytest.approx(30.0, abs=0.01)

    total = sum(h["value_usd"] for h in top_holdings.values())
    expected = (ETH_QTY * ETH_PRICE + ETH_NATIVE_TOKENS_VALUE) + (SOL_QTY * SOL_PRICE + SOL_NATIVE_TOKENS_VALUE)
    assert total == pytest.approx(expected, abs=0.01)
