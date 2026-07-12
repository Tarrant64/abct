"""
Unit tests for SEC-A1: the /portfolio/summary cache must be partitioned by the
include_sparklines request variant. Before the fix, both variants shared one
cache key, so a sparkline-less mobile request's SWR background recompute could
overwrite the sparkline-full payload other clients (watchOS) read.

Covered here:
- the key builder yields distinct, stable keys per (user, variant);
- fresh-hit path serves the row matching the requested variant only;
- miss path computes and writes each variant to its own row;
- SWR stale path: background recompute of one variant never overwrites the
  other variant's row (the actual advisory);
- refresh=true still bypasses the cache and only rewrites its own variant;
- legacy unpartitioned rows are unreachable, unserved, and cause no errors.

The real _compute_mobile_portfolio_summary runs in most tests, with upstream
services stubbed and the cache layer replaced by an in-memory store, so the
cache-key construction inside the compute/write path is genuinely exercised.
"""

import asyncio
import os
import sys
import types

# Add backend to sys.path so imports work
BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import routers.mobile as mobile  # noqa: E402
import services.offchain_helpers as offchain_helpers  # noqa: E402

USER = 7
LEGACY_KEY = f"mobile_portfolio_summary_{USER}"  # pre-SEC-A1 unpartitioned key


class FakeCacheStore:
    """In-memory stand-in for database get_cache/get_stale_cache/set_cache.

    Rows in `fresh` behave as unexpired; rows only in `store` behave as
    expired-but-present (the stale/SWR case).
    """

    def __init__(self):
        self.store = {}
        self.fresh = set()

    def seed(self, key, value, fresh=True):
        self.store[key] = value
        if fresh:
            self.fresh.add(key)

    async def get_cache(self, key, user_id=None):
        return self.store[key] if key in self.fresh else None

    async def get_stale_cache(self, key, user_id=None):
        if key in self.store:
            return self.store[key], "2026-01-01T00:00:00"
        return None, None

    async def set_cache(self, key, value, ttl_seconds=300, user_id=None):
        self.store[key] = value
        self.fresh.add(key)


def _install_fake_cache(monkeypatch):
    cache = FakeCacheStore()
    monkeypatch.setattr(mobile, "get_cache", cache.get_cache)
    monkeypatch.setattr(mobile, "get_stale_cache", cache.get_stale_cache)
    monkeypatch.setattr(mobile, "set_cache", cache.set_cache)
    return cache


def _stub_compute_upstreams(monkeypatch):
    """Stub every external await inside _compute_mobile_portfolio_summary so
    the real function (and its real cache-key construction) runs offline.
    Returns a recorder of sparkline-fetch and portfolio-refresh calls."""
    recorder = {"sparkline_calls": 0, "portfolio_refresh_args": []}

    async def get_portfolio_summary(user_id, refresh):
        recorder["portfolio_refresh_args"].append(refresh)
        return {}

    async def get_portfolio_totals(user_id, refresh=False):
        return {"staking_usd": 0, "defi_usd": 0, "tracked_tokens_usd": 0}

    async def get_all_native_assets(user_id):
        return {"valuable_assets": []}

    portfolio_stub = types.SimpleNamespace(
        get_portfolio_summary=get_portfolio_summary,
        get_portfolio_totals=get_portfolio_totals,
        get_all_native_assets=get_all_native_assets,
    )

    async def get_all_exchanges_summary(user_id):
        return {"total_usd": 0}

    async def get_all_chains_nft_summary(user_id):
        return {"total_value_usd": 0, "chains": {}}

    async def get_defi_summary(user_id):
        return {"all_positions": []}

    async def get_all_tracked_prices():
        return {}

    async def get_all_wallets(user_id):
        return []

    async def get_staking_value(all_prices, user_id=None):
        return 0

    async def fetch_sparklines(symbols, max_points=24):
        recorder["sparkline_calls"] += 1
        return {}

    monkeypatch.setattr(mobile, "portfolio", portfolio_stub)
    monkeypatch.setattr(
        mobile, "exchanges",
        types.SimpleNamespace(get_all_exchanges_summary=get_all_exchanges_summary))
    monkeypatch.setattr(
        mobile, "nfts",
        types.SimpleNamespace(get_all_chains_nft_summary=get_all_chains_nft_summary))
    monkeypatch.setattr(
        mobile, "defi", types.SimpleNamespace(get_defi_summary=get_defi_summary))
    monkeypatch.setattr(
        mobile, "pricing_service",
        types.SimpleNamespace(get_all_tracked_prices=get_all_tracked_prices))
    monkeypatch.setattr(mobile, "get_all_wallets", get_all_wallets)
    monkeypatch.setattr(offchain_helpers, "get_staking_value", get_staking_value)
    monkeypatch.setattr(mobile, "_fetch_asset_sparklines", fetch_sparklines)
    return recorder


async def _wait_until(cond, timeout=2.0):
    for _ in range(int(timeout / 0.01)):
        if cond():
            return True
        await asyncio.sleep(0.01)
    return cond()


def test_cache_key_partitions_by_variant():
    with_sparks = mobile._summary_cache_key(USER, True)
    without_sparks = mobile._summary_cache_key(USER, False)
    assert with_sparks != without_sparks
    assert with_sparks != LEGACY_KEY and without_sparks != LEGACY_KEY
    # Stable per (user, variant), distinct across users
    assert with_sparks == mobile._summary_cache_key(USER, True)
    assert with_sparks != mobile._summary_cache_key(USER + 1, True)


async def test_fresh_hit_serves_matching_variant_only(monkeypatch):
    cache = _install_fake_cache(monkeypatch)
    sparks_payload = {"total_value_usd": 1, "variant": "sparks"}
    nosparks_payload = {"total_value_usd": 2, "variant": "nosparks"}
    cache.seed(mobile._summary_cache_key(USER, True), sparks_payload)
    cache.seed(mobile._summary_cache_key(USER, False), nosparks_payload)

    async def compute_must_not_run(user_id, refresh, include_sparklines):
        raise AssertionError("fresh hit must not recompute")

    monkeypatch.setattr(
        mobile, "_compute_mobile_portfolio_summary", compute_must_not_run)

    assert await mobile.get_mobile_portfolio_summary(
        user_id=USER, refresh=False, include_sparklines=True) == sparks_payload
    assert await mobile.get_mobile_portfolio_summary(
        user_id=USER, refresh=False, include_sparklines=False) == nosparks_payload


async def test_miss_computes_and_writes_distinct_rows(monkeypatch):
    cache = _install_fake_cache(monkeypatch)
    recorder = _stub_compute_upstreams(monkeypatch)

    result_sparks = await mobile.get_mobile_portfolio_summary(
        user_id=USER, refresh=False, include_sparklines=True)
    assert recorder["sparkline_calls"] == 1
    result_nosparks = await mobile.get_mobile_portfolio_summary(
        user_id=USER, refresh=False, include_sparklines=False)
    assert recorder["sparkline_calls"] == 1  # no-sparkline variant skips fetch

    keys = set(cache.store)
    assert keys == {
        mobile._summary_cache_key(USER, True),
        mobile._summary_cache_key(USER, False),
    }
    assert cache.store[mobile._summary_cache_key(USER, True)] == result_sparks
    assert cache.store[mobile._summary_cache_key(USER, False)] == result_nosparks
    assert result_sparks["from_cache"] is False


async def test_swr_recompute_does_not_overwrite_other_variant(monkeypatch):
    """ADVISORY-1: a stale no-sparklines request must background-recompute
    only its own row; the sparkline-full row other clients read stays put."""
    cache = _install_fake_cache(monkeypatch)
    _stub_compute_upstreams(monkeypatch)

    sparks_key = mobile._summary_cache_key(USER, True)
    nosparks_key = mobile._summary_cache_key(USER, False)
    stale_sparks = {"total_value_usd": 111, "variant": "sparks-stale"}
    stale_nosparks = {"total_value_usd": 222, "variant": "nosparks-stale"}
    cache.seed(sparks_key, stale_sparks, fresh=False)
    cache.seed(nosparks_key, stale_nosparks, fresh=False)

    served = await mobile.get_mobile_portfolio_summary(
        user_id=USER, refresh=False, include_sparklines=False)
    assert served == stale_nosparks  # stale payload served immediately
    assert nosparks_key in mobile._summary_refresh_tasks

    assert await _wait_until(lambda: not mobile._summary_refresh_tasks)
    assert cache.store[nosparks_key] != stale_nosparks  # own row recomputed
    assert cache.store[sparks_key] == stale_sparks      # other variant intact
    assert nosparks_key in cache.fresh


async def test_refresh_true_recomputes_only_its_variant(monkeypatch):
    cache = _install_fake_cache(monkeypatch)
    recorder = _stub_compute_upstreams(monkeypatch)

    sparks_key = mobile._summary_cache_key(USER, True)
    nosparks_key = mobile._summary_cache_key(USER, False)
    old_sparks = {"total_value_usd": 111, "variant": "sparks-old"}
    old_nosparks = {"total_value_usd": 222, "variant": "nosparks-old"}
    cache.seed(sparks_key, old_sparks)
    cache.seed(nosparks_key, old_nosparks)

    served = await mobile.get_mobile_portfolio_summary(
        user_id=USER, refresh=True, include_sparklines=True)
    assert served != old_sparks
    assert recorder["portfolio_refresh_args"] == [True]  # force-refresh passed through
    assert cache.store[sparks_key] == served
    assert cache.store[nosparks_key] == old_nosparks  # other variant untouched


async def test_legacy_unpartitioned_row_is_ignored_without_error(monkeypatch):
    cache = _install_fake_cache(monkeypatch)
    _stub_compute_upstreams(monkeypatch)
    legacy_payload = {"total_value_usd": 999, "variant": "legacy"}
    cache.seed(LEGACY_KEY, legacy_payload)  # fresh legacy row present

    for include_sparklines in (True, False):
        result = await mobile.get_mobile_portfolio_summary(
            user_id=USER, refresh=False, include_sparklines=include_sparklines)
        assert result != legacy_payload  # legacy row never served

    assert not mobile._summary_refresh_tasks  # no SWR scheduled off legacy row
    assert cache.store[LEGACY_KEY] == legacy_payload  # left alone to age out
