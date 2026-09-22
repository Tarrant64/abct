"""
Unit tests for ABCT-MOBILE-VALUE-MISMATCH-20260921 (symptom 1):

The mobile Overview chart (/api/mobile/chart/portfolio-history, which calls
portfolio.get_unified_chart() for every range except 24h, and
portfolio.get_24h_hourly_chart() for range=24h) never learned about the
include_nfts_in_total preference added by ABCT-NFT-TOGGLE-20260919. That
preference already gates /portfolio/summary's header total (default: NFTs
EXCLUDED, since NFT floor prices are stale) and portfolio.get_portfolio_history
(the web dashboard's own chart, already covered by test_nft_toggle.py) -- but
wallet_daily_balances rows and get_portfolio_totals()['nft_usd'] always carry
NFT value baked in regardless of the preference, so the two chart functions
kept re-including it. Result: the chart's latest point sat above the header
total by exactly the (stale, excluded-by-default) NFT value.

These tests mirror test_nft_toggle.py's pattern for get_portfolio_history and
assert the same subtract-when-excluded behavior for both chart functions, plus
that the NFT preference is part of each function's cache key (a toggle must
not be masked by a row cached under the other setting).
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402
import routers.portfolio as portfolio  # noqa: E402

USER_ID = 4343
NFT_VALUE_USD = 1234.56


async def _async_none():
    return None


def _bool_fixture(value):
    async def _inner(user_id):
        return value
    return _inner


class _NullCache:
    """No-op get_cache/set_cache -- every call is a cache miss."""

    async def get_cache(self, key, user_id=None):
        return None

    async def set_cache(self, key, value, ttl_seconds=300, user_id=None):
        return None


def _install_null_cache(monkeypatch):
    cache = _NullCache()
    monkeypatch.setattr(portfolio, "get_cache", cache.get_cache)
    monkeypatch.setattr(portfolio, "set_cache", cache.set_cache)


# ---------------------------------------------------------------------------
# get_unified_chart
# ---------------------------------------------------------------------------

ON_CHAIN_VALUE = 13000.0
EXCHANGE_VALUE = 1109.58
# total_value is deliberately the sum of every component below (including
# NFTs) so the on_chain + off_chain == total identity is meaningful to
# assert, matching how the snapshot writer actually builds this row
# (services/snapshot.py sums every component, NFTs included, unconditionally).
TOTAL_VALUE_WITH_NFTS = ON_CHAIN_VALUE + EXCHANGE_VALUE + NFT_VALUE_USD


async def _wdb_rows_fixture():
    return [{
        "date": "2026-09-20",
        "total_value": TOTAL_VALUE_WITH_NFTS,
        "on_chain_value": ON_CHAIN_VALUE,
        "exchange_value": EXCHANGE_VALUE,
        "staking_value": 0.0,
        "defi_value": 0.0,
        "nft_value": NFT_VALUE_USD,
        "tracked_tokens_value": 0.0,
        "custom_tokens_value": 0.0,
    }]


async def _run_unified_chart(monkeypatch, include_nfts: bool):
    _install_null_cache(monkeypatch)
    monkeypatch.setattr(portfolio, "get_username_by_user_id", lambda user_id: _async_none())
    monkeypatch.setattr(database, "get_unified_daily_totals",
                         lambda user_id, start_date=None: _wdb_rows_fixture())
    monkeypatch.setattr(portfolio, "get_nft_inclusion_preference", _bool_fixture(include_nfts))
    return await portfolio.get_unified_chart(user_id=USER_ID, range="1w", by_chain=False)


async def test_unified_chart_excludes_nfts_by_default(monkeypatch):
    result = await _run_unified_chart(monkeypatch, include_nfts=False)
    point = result["data"][0]
    # Informational breakdown always reports the raw NFT component...
    assert point["breakdown"]["components"]["nfts"] == pytest.approx(NFT_VALUE_USD)
    # ...but the total (what the mobile chart plots) has it subtracted.
    assert point["total_value"] == pytest.approx(TOTAL_VALUE_WITH_NFTS - NFT_VALUE_USD)
    # ABCT-MOBILE-VALUE-MISMATCH-20260921-B: off_chain_value_usd is a
    # component surfaced directly to the client and must be gated the same
    # way as total, not just total on its own -- otherwise on_chain +
    # off_chain != total, and off_chain alone silently re-exposes NFT value.
    assert point["off_chain_value"] == pytest.approx(EXCHANGE_VALUE)
    assert point["on_chain_value"] + point["off_chain_value"] == pytest.approx(point["total_value"])


async def test_unified_chart_includes_nfts_when_enabled(monkeypatch):
    result = await _run_unified_chart(monkeypatch, include_nfts=True)
    point = result["data"][0]
    assert point["total_value"] == pytest.approx(TOTAL_VALUE_WITH_NFTS)
    assert point["off_chain_value"] == pytest.approx(EXCHANGE_VALUE + NFT_VALUE_USD)
    assert point["on_chain_value"] + point["off_chain_value"] == pytest.approx(point["total_value"])


async def test_unified_chart_cache_key_varies_with_preference(monkeypatch):
    """A toggle must take effect immediately, not wait out a stale cached
    row computed under the other setting."""
    seen_keys = []

    class RecordingCache(_NullCache):
        async def get_cache(self, key, user_id=None):
            seen_keys.append(key)
            return None

    monkeypatch.setattr(portfolio, "get_cache", RecordingCache().get_cache)
    monkeypatch.setattr(portfolio, "set_cache", _NullCache().set_cache)
    monkeypatch.setattr(portfolio, "get_username_by_user_id", lambda user_id: _async_none())
    monkeypatch.setattr(database, "get_unified_daily_totals",
                         lambda user_id, start_date=None: _wdb_rows_fixture())

    monkeypatch.setattr(portfolio, "get_nft_inclusion_preference", _bool_fixture(False))
    await portfolio.get_unified_chart(user_id=USER_ID, range="1w", by_chain=False)
    monkeypatch.setattr(portfolio, "get_nft_inclusion_preference", _bool_fixture(True))
    await portfolio.get_unified_chart(user_id=USER_ID, range="1w", by_chain=False)

    assert len(seen_keys) == 2
    assert seen_keys[0] != seen_keys[1]


# ---------------------------------------------------------------------------
# get_24h_hourly_chart
# ---------------------------------------------------------------------------

async def _totals_fixture():
    return {
        "staking_usd": 0.0,
        "defi_usd": 0.0,
        "exchange_usd": 100.0,
        "nft_usd": NFT_VALUE_USD,
        "tracked_tokens_usd": 0.0,
        "custom_tokens_usd": 0.0,
    }


async def _summary_fixture():
    return {"cardano": {"total_ada": 1000.0}}


async def _historical_prices_fixture(symbols, days=1):
    return {"ADA": [
        {"date": "2026-09-20 12:00", "price": 0.24, "time": 0},
        {"date": "2026-09-20 13:00", "price": 0.25, "time": 3600},
    ]}


async def _run_24h_chart(monkeypatch, include_nfts: bool):
    _install_null_cache(monkeypatch)
    monkeypatch.setattr(portfolio, "get_portfolio_summary", lambda user_id, refresh=False: _summary_fixture())
    monkeypatch.setattr(portfolio, "get_portfolio_totals", lambda user_id: _totals_fixture())
    monkeypatch.setattr(portfolio.pricing_service, "get_historical_prices", _historical_prices_fixture)
    monkeypatch.setattr(portfolio, "get_nft_inclusion_preference", _bool_fixture(include_nfts))
    return await portfolio.get_24h_hourly_chart(user_id=USER_ID, refresh=False)


async def test_24h_chart_excludes_nfts_by_default(monkeypatch):
    result = await _run_24h_chart(monkeypatch, include_nfts=False)
    assert result["data"], "expected at least one hourly point"
    for point in result["data"]:
        # Informational breakdown still reports the raw NFT component...
        assert point["breakdown"]["components"]["nfts"] == pytest.approx(NFT_VALUE_USD)
        # ...but it must not be present in total_value/off_chain_value.
        assert point["off_chain_value"] == pytest.approx(100.0)  # exchange only, no NFT
        assert point["total_value"] == pytest.approx(point["on_chain_value"] + 100.0)


async def test_24h_chart_includes_nfts_when_enabled(monkeypatch):
    result = await _run_24h_chart(monkeypatch, include_nfts=True)
    for point in result["data"]:
        assert point["off_chain_value"] == pytest.approx(100.0 + NFT_VALUE_USD)
        assert point["total_value"] == pytest.approx(
            point["on_chain_value"] + 100.0 + NFT_VALUE_USD)


async def test_24h_chart_cache_key_varies_with_preference(monkeypatch):
    seen_keys = []

    class RecordingCache(_NullCache):
        async def get_cache(self, key, user_id=None):
            seen_keys.append(key)
            return None

    monkeypatch.setattr(portfolio, "get_cache", RecordingCache().get_cache)
    monkeypatch.setattr(portfolio, "set_cache", _NullCache().set_cache)
    monkeypatch.setattr(portfolio, "get_portfolio_summary", lambda user_id, refresh=False: _summary_fixture())
    monkeypatch.setattr(portfolio, "get_portfolio_totals", lambda user_id: _totals_fixture())
    monkeypatch.setattr(portfolio.pricing_service, "get_historical_prices", _historical_prices_fixture)

    monkeypatch.setattr(portfolio, "get_nft_inclusion_preference", _bool_fixture(False))
    await portfolio.get_24h_hourly_chart(user_id=USER_ID, refresh=False)
    monkeypatch.setattr(portfolio, "get_nft_inclusion_preference", _bool_fixture(True))
    await portfolio.get_24h_hourly_chart(user_id=USER_ID, refresh=False)

    assert len(seen_keys) == 2
    assert seen_keys[0] != seen_keys[1]
