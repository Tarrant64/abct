"""
Regression tests for ABCT-BACKEND-QTYCACHE-20260918.

Root cause: /portfolio/summary's outer cache (portfolio_summary_{user_id})
was pinned to CACHE_TTL_PERSISTENT (7 days). That fully shadowed the
per-wallet cache inside fetch_wallet_data (wallet_balance_{wallet_id},
WALLET_DATA_CACHE_TTL = 300s) -- once the summary was cached, the per-wallet
fan-out (and therefore get_wallet_balance/get_wallet_assets, which are plain
local DB reads) never ran again for up to 7 days without an explicit
refresh=True. Quantities looked frozen even though nothing about fetching
them was actually expensive.

Fix (routers/portfolio.py): PORTFOLIO_CACHE_TTL now derives from
WALLET_DATA_CACHE_TTL (single source of truth), so the summary naturally
re-runs its per-wallet fan-out at most every WALLET_DATA_CACHE_TTL seconds,
and that fan-out's own per-wallet cache still bounds how many external calls
a recompute makes -- cost does not grow just because the outer TTL shrank.

These tests exercise the real get_portfolio_summary with the database cache
layer and the one genuinely-external, uncached call in the per-wallet
fan-out (cardano_service.get_stake_address -- see scope doc, it has no
caching at its own layer) replaced by fakes. calculate_wallet_native_assets_value
(USD valuation via Koios/pricing) is stubbed out here since it is a separate
concern from the quantity fields (balance / native_assets_count) this bug
report is about.

Covered:
1. test_summary_reflects_balance_change_without_refresh -- a plain GET
   (refresh=False) picks up a new balance row once the shared TTL has
   elapsed, without ever passing refresh=True.
2. test_stale_cache_ttl_no_longer_hides_balance_for_a_week -- same as above,
   but asserts the recompute happens within one WALLET_DATA_CACHE_TTL window,
   not after the old 7-day TTL (guards against a partial revert).
3. test_recompute_external_call_count_is_bounded_per_wallet -- the number of
   get_stake_address calls across two cache windows is exactly
   2 * wallet_count, proving cost is bounded and proportional, not unbounded
   or duplicated per request.
4. test_portfolio_cache_ttl_matches_wallet_cache_ttl -- guards the constant
   relationship itself so a future edit can't silently re-shadow the
   per-wallet cache by changing one TTL and not the other.
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import routers.portfolio as portfolio  # noqa: E402
import config  # noqa: E402

USER_ID = 42
WALLET_ID = 1
ADDRESS = "addr1qxytest0000000000000000000000000000000000000000000000000"


class FakeClock:
    """Controllable clock so tests can cross TTL boundaries deterministically."""

    def __init__(self):
        self.now = 0.0

    def advance(self, seconds: float):
        self.now += seconds


class FakeCache:
    """In-memory stand-in for database.get_cache/set_cache/clear_cache.

    Honors ttl_seconds against the injected FakeClock instead of wall-clock
    time, so tests can cross a TTL boundary with clock.advance() rather than
    real sleeps.
    """

    def __init__(self, clock: FakeClock):
        self.clock = clock
        self.store = {}  # key -> (value, expires_at)

    async def get_cache(self, key, user_id=None):
        entry = self.store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if self.clock.now >= expires_at:
            return None
        return value

    async def set_cache(self, key, value, ttl_seconds=300, user_id=None):
        self.store[key] = (value, self.clock.now + ttl_seconds)

    async def clear_cache(self, key_pattern=None, user_id=None):
        if key_pattern is None:
            self.store.clear()
            return
        for k in [k for k in self.store if k.startswith(key_pattern)]:
            del self.store[k]


def _cardano_wallet():
    return {
        "id": WALLET_ID,
        "blockchain": "cardano",
        "address": ADDRESS,
        "label": "Test Wallet",
        "updated_at": None,
    }


def _install_common_fakes(monkeypatch, clock, wallets, balance_state, stake_calls):
    """Wire fakes for everything get_portfolio_summary needs except the
    per-scenario cache and get_all_wallets, which callers set up themselves."""

    async def fake_get_username_by_user_id(user_id):
        return "tester"

    async def fake_is_demo_user(username):
        return False

    async def fake_get_wallet_balance(wallet_id):
        return dict(balance_state)

    async def fake_get_wallet_assets(wallet_id):
        return []

    async def fake_calculate_wallet_native_assets_value(wallet_id, blockchain, user_id):
        return 0.0

    async def fake_get_stake_address(address):
        stake_calls.append(address)
        return None  # no stake grouping needed for these tests

    monkeypatch.setattr(portfolio, "get_username_by_user_id", fake_get_username_by_user_id)
    monkeypatch.setattr(portfolio, "is_demo_user", fake_is_demo_user)
    monkeypatch.setattr(portfolio, "get_all_wallets", lambda user_id=None: _async_return(wallets))
    monkeypatch.setattr(portfolio, "get_wallet_balance", fake_get_wallet_balance)
    monkeypatch.setattr(portfolio, "get_wallet_assets", fake_get_wallet_assets)
    monkeypatch.setattr(
        portfolio,
        "calculate_wallet_native_assets_value",
        fake_calculate_wallet_native_assets_value,
    )
    monkeypatch.setattr(portfolio.cardano_service, "get_stake_address", fake_get_stake_address)


async def _async_return(value):
    return value


@pytest.mark.asyncio
async def test_summary_reflects_balance_change_without_refresh(monkeypatch):
    clock = FakeClock()
    cache = FakeCache(clock)
    monkeypatch.setattr(portfolio, "get_cache", cache.get_cache)
    monkeypatch.setattr(portfolio, "set_cache", cache.set_cache)

    balance_state = {"amount": "10.0"}
    stake_calls = []
    _install_common_fakes(monkeypatch, clock, [_cardano_wallet()], balance_state, stake_calls)

    # Cold call: populates both the summary cache and the per-wallet cache.
    result = await portfolio.get_portfolio_summary(user_id=USER_ID, refresh=False)
    assert result["cardano"]["total_ada"] == 10.0

    # Balance changes in the DB (e.g. a real wallet sync wrote a new row) --
    # but we're still inside the TTL window, so the warm cache should still
    # serve the old value. This is expected, not the bug under test.
    balance_state["amount"] = "25.0"
    result = await portfolio.get_portfolio_summary(user_id=USER_ID, refresh=False)
    assert result["cardano"]["total_ada"] == 10.0

    # Cross the TTL boundary. A plain refresh=False call must now pick up
    # the new balance -- this is the actual regression: before the fix this
    # required refresh=True for up to 7 days.
    clock.advance(portfolio.PORTFOLIO_CACHE_TTL + 1)
    result = await portfolio.get_portfolio_summary(user_id=USER_ID, refresh=False)
    assert result["cardano"]["total_ada"] == 25.0


@pytest.mark.asyncio
async def test_stale_cache_ttl_no_longer_hides_balance_for_a_week(monkeypatch):
    clock = FakeClock()
    cache = FakeCache(clock)
    monkeypatch.setattr(portfolio, "get_cache", cache.get_cache)
    monkeypatch.setattr(portfolio, "set_cache", cache.set_cache)

    balance_state = {"amount": "1.0"}
    stake_calls = []
    _install_common_fakes(monkeypatch, clock, [_cardano_wallet()], balance_state, stake_calls)

    await portfolio.get_portfolio_summary(user_id=USER_ID, refresh=False)
    balance_state["amount"] = "2.0"

    # One second before the (old) 7-day TTL would have expired, the fix
    # should already have refreshed -- prove the wait is bounded by
    # WALLET_DATA_CACHE_TTL, not by the old CACHE_TTL_PERSISTENT.
    assert portfolio.PORTFOLIO_CACHE_TTL < 86400  # much less than even 1 day
    clock.advance(portfolio.PORTFOLIO_CACHE_TTL + 1)

    result = await portfolio.get_portfolio_summary(user_id=USER_ID, refresh=False)
    assert result["cardano"]["total_ada"] == 2.0


@pytest.mark.asyncio
async def test_recompute_external_call_count_is_bounded_per_wallet(monkeypatch):
    clock = FakeClock()
    cache = FakeCache(clock)
    monkeypatch.setattr(portfolio, "get_cache", cache.get_cache)
    monkeypatch.setattr(portfolio, "set_cache", cache.set_cache)

    wallets = [
        {**_cardano_wallet(), "id": i, "address": f"{ADDRESS}{i}"} for i in range(3)
    ]
    balance_state = {"amount": "1.0"}
    stake_calls = []
    _install_common_fakes(monkeypatch, clock, wallets, balance_state, stake_calls)

    # Window 1: cold summary cache AND cold per-wallet caches -> exactly one
    # get_stake_address call per wallet.
    await portfolio.get_portfolio_summary(user_id=USER_ID, refresh=False)
    assert len(stake_calls) == 3

    # Immediately repeating the read within the TTL window must not add any
    # further calls -- both the summary cache and (if it were ever reached)
    # the per-wallet cache are still warm.
    await portfolio.get_portfolio_summary(user_id=USER_ID, refresh=False)
    assert len(stake_calls) == 3

    # Window 2: cross the shared TTL boundary once. Exactly one more call per
    # wallet -- cost is proportional to wallet count and window count, not
    # unbounded and not duplicated per request.
    clock.advance(portfolio.PORTFOLIO_CACHE_TTL + 1)
    await portfolio.get_portfolio_summary(user_id=USER_ID, refresh=False)
    assert len(stake_calls) == 6


def test_portfolio_cache_ttl_matches_wallet_cache_ttl():
    """Guard against silently re-introducing the shadowing bug: if someone
    edits PORTFOLIO_CACHE_TTL back to a long-lived constant without also
    touching WALLET_DATA_CACHE_TTL, the two drift apart and the outer cache
    shadows the inner one again."""
    assert portfolio.PORTFOLIO_CACHE_TTL == portfolio.WALLET_DATA_CACHE_TTL
    assert portfolio.PORTFOLIO_CACHE_TTL < 3600  # well under an hour, nowhere near 7 days


def test_portfolio_quantity_cache_ttl_is_the_perf_stopgap_value():
    """ABCT-SUMMARY-PERF-20260919: guards the specific 20-minute stopgap
    value (and that it's still the source for both TTLs) so a future edit
    doesn't silently drift back toward the 5-minute setting that turned a
    ~weekly expensive recompute into a ~every-5-minutes one."""
    assert config.PORTFOLIO_QUANTITY_CACHE_TTL_SECONDS == 1200  # 20 minutes
    assert portfolio.PORTFOLIO_CACHE_TTL == config.PORTFOLIO_QUANTITY_CACHE_TTL_SECONDS
    assert portfolio.WALLET_DATA_CACHE_TTL == config.PORTFOLIO_QUANTITY_CACHE_TTL_SECONDS


def test_portfolio_quantity_cache_ttl_is_decoupled_from_cache_ttl_hot():
    """ABCT-SUMMARY-PERF-20260919 deliberately split this off from
    CACHE_TTL_HOT (which also governs unrelated caches -- prices, exchange
    balances) so that tuning one doesn't silently move the other. Guards
    against re-merging them back into a single shared constant."""
    assert config.PORTFOLIO_QUANTITY_CACHE_TTL_SECONDS != config.CACHE_TTL_HOT
