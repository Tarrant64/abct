"""
ABCT-MOBILE-PERF-20261103 regression tests.

Deploy evidence (2026-11-03, inside the abct-dashboard container against
uvicorn directly): the chart endpoints and refresh=true computed full
provider fan-outs IN-REQUEST (17-20 s each), blocking the single-worker
event loop so the app's 5-request open burst starved past the client's
20 s receiveTimeout — even the 0.01 s summary call.

Contracts locked here:
- a slow/hung summary compute must never block a concurrent fast call;
- refresh=true answers from the cache immediately (background hard pull);
- cold-cache requests bounded-wait and 503 instead of computing inline;
- the chart path never computes a summary (cache-only live-total override);
- the 24h chart's cold compute is bounded and deduped;
- Alchemy 429 sets a no-HTTP-call cooldown;
- the scheduler's no-provider warning is throttled.
"""

import asyncio
import os
import sys
import time
from datetime import datetime, timedelta

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import routers.mobile as mobile  # noqa: E402
import routers.portfolio as portfolio  # noqa: E402
from fastapi import HTTPException  # noqa: E402

USER = 7
PAYLOAD = {"total_value_usd": 1234.0, "variant": "computed"}


class FakeCacheStore:
    """Same shape as test_summary_cache_variants.FakeCacheStore (standalone
    copy so the two suites evolve independently)."""

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
            return self.store[key], (datetime.now() - timedelta(seconds=1)).isoformat()
        return None, None

    async def set_cache(self, key, value, ttl_seconds=300, user_id=None):
        self.store[key] = value
        self.fresh.add(key)


def _install_cache(monkeypatch, store):
    monkeypatch.setattr(mobile, "get_cache", store.get_cache)
    monkeypatch.setattr(mobile, "get_stale_cache", store.get_stale_cache)
    monkeypatch.setattr(mobile, "set_cache", store.set_cache)


async def _wait_until(cond, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        await asyncio.sleep(0.01)
    return cond()


async def _drain_summary_tasks():
    ok = await _wait_until(lambda: not mobile._summary_refresh_tasks)
    assert ok, "background summary refresh did not finish"


@pytest.fixture
def clean_slots():
    mobile._summary_refresh_tasks.clear()
    portfolio._24h_compute_tasks.clear()
    yield
    mobile._summary_refresh_tasks.clear()
    portfolio._24h_compute_tasks.clear()


# ---------------------------------------------------------------------------
# 1. Burst: a slow compute must not block the fast calls
# ---------------------------------------------------------------------------

async def test_burst_slow_compute_does_not_block_fast_calls(monkeypatch, clean_slots):
    """Mirror of the deploy burst: refresh summary + plain summary + a
    fast call, all concurrent, with the summary compute taking 3 s. The
    fast call must finish ~immediately; the summary calls must give up
    (503) at the bounded wait instead of holding ~3 s+ inline."""
    store = FakeCacheStore()
    _install_cache(monkeypatch, store)
    monkeypatch.setattr(mobile, "MOBILE_REFRESH_BOUNDED_WAIT_S", 0.5)

    compute_done_at = {}

    async def slow_compute(user_id, refresh, include_sparklines):
        await asyncio.sleep(3.0)  # the "provider fan-out"
        await store.set_cache(mobile._summary_cache_key(user_id, include_sparklines),
                              dict(PAYLOAD))
        compute_done_at["t"] = time.monotonic()
        return dict(PAYLOAD)

    monkeypatch.setattr(mobile, "_compute_mobile_portfolio_summary", slow_compute)

    fast_finished_at = {}

    async def fast_call():  # stands in for the 0.01 s instant/summary hit
        await asyncio.sleep(0.01)
        fast_finished_at["t"] = time.monotonic()
        return "fast"

    async def summary(refresh):
        return await mobile.get_mobile_portfolio_summary(
            user_id=USER, refresh=refresh, include_sparklines=False)

    t0 = time.monotonic()
    results = await asyncio.gather(
        summary(refresh=True), summary(refresh=False), fast_call(),
        return_exceptions=True)
    elapsed = time.monotonic() - t0

    fast_result = results[2]
    assert fast_result == "fast"
    # The fast call finished ~immediately — the event loop was never held.
    assert fast_finished_at["t"] - t0 < 1.0, \
        f"fast call starved for {fast_finished_at['t'] - t0:.2f}s"
    # Both summary calls 503'd at the bounded wait (~0.5 s), not 2x3 s serial.
    for r in results[:2]:
        assert isinstance(r, HTTPException) and r.status_code == 503, r
    assert elapsed < 2.0, f"burst took {elapsed:.2f}s — inline compute leaked"

    # The compute kept running and its row is now the retry's cache hit.
    await _drain_summary_tasks()
    t1 = time.monotonic()
    served = await summary(refresh=True)
    assert served == PAYLOAD
    assert time.monotonic() - t1 < 1.0


async def test_refresh_with_fresh_cache_answers_immediately_despite_hung_compute(
        monkeypatch, clean_slots):
    store = FakeCacheStore()
    _install_cache(monkeypatch, store)
    store.seed(mobile._summary_cache_key(USER, False), {"total_value_usd": 42.0})

    release = asyncio.Event()

    async def hung_compute(user_id, refresh, include_sparklines):
        await release.wait()
        return {}

    monkeypatch.setattr(mobile, "_compute_mobile_portfolio_summary", hung_compute)

    t0 = time.monotonic()
    served = await mobile.get_mobile_portfolio_summary(
        user_id=USER, refresh=True, include_sparklines=False)
    assert time.monotonic() - t0 < 1.0
    assert served == {"total_value_usd": 42.0}
    assert mobile._summary_refresh_tasks  # hard pull scheduled, deduped

    release.set()
    await _drain_summary_tasks()


async def test_refresh_serves_stale_servable_row_instead_of_waiting(monkeypatch, clean_slots):
    """A stale-but-within-cap row is 'current data' for a hard pull too:
    answered immediately, hard pull still scheduled."""
    store = FakeCacheStore()
    _install_cache(monkeypatch, store)
    # Seed as NOT fresh -> get_cache misses, get_stale_cache hits.
    store.seed(mobile._summary_cache_key(USER, False), {"total_value_usd": 42.0},
               fresh=False)
    monkeypatch.setattr(mobile, "MOBILE_REFRESH_BOUNDED_WAIT_S", 0.5)

    release = asyncio.Event()

    async def hung_compute(user_id, refresh, include_sparklines):
        await release.wait()
        return {}

    monkeypatch.setattr(mobile, "_compute_mobile_portfolio_summary", hung_compute)

    t0 = time.monotonic()
    served = await mobile.get_mobile_portfolio_summary(
        user_id=USER, refresh=True, include_sparklines=False)
    assert time.monotonic() - t0 < 1.0
    assert served == {"total_value_usd": 42.0}
    assert mobile._summary_refresh_tasks  # hard pull still deduped in background

    release.set()
    await _drain_summary_tasks()


async def test_refresh_true_propagates_force_refresh(monkeypatch, clean_slots):
    """The background hard pull must recompute the staking/defi buckets (D2):
    refresh=True reaches _compute_mobile_portfolio_summary."""
    store = FakeCacheStore()
    _install_cache(monkeypatch, store)
    store.seed(mobile._summary_cache_key(USER, True), {"total_value_usd": 1.0})

    seen = {}

    async def fake_compute(user_id, refresh, include_sparklines):
        seen["refresh"] = refresh
        await store.set_cache(mobile._summary_cache_key(user_id, include_sparklines),
                              {"total_value_usd": 2.0})
        return {}

    monkeypatch.setattr(mobile, "_compute_mobile_portfolio_summary", fake_compute)

    served = await mobile.get_mobile_portfolio_summary(
        user_id=USER, refresh=True, include_sparklines=True)
    assert served == {"total_value_usd": 1.0}
    await _drain_summary_tasks()
    assert seen["refresh"] is True


# ---------------------------------------------------------------------------
# 2. Chart path: cache-only live-total override
# ---------------------------------------------------------------------------

def _chart_points():
    return [
        {"date": "2026-11-02", "total_value": 100.0,
         "on_chain_value": 100.0, "off_chain_value": 0.0,
         "breakdown": {"chains": {}, "components": {}}},
        {"date": "2026-11-03", "total_value": 101.0,
         "on_chain_value": 101.0, "off_chain_value": 0.0,
         "breakdown": {"chains": {}, "components": {}}},
    ]


@pytest.fixture
def chart_env(monkeypatch):
    store = FakeCacheStore()
    _install_cache(monkeypatch, store)

    async def fake_username(user_id):
        return "chris"

    async def fake_is_demo(username):
        return False

    monkeypatch.setattr(mobile, "get_username_by_user_id", fake_username)
    monkeypatch.setattr(mobile, "is_demo_user", fake_is_demo)

    async def must_not_compute(user_id, refresh, include_sparklines):
        raise AssertionError(
            "chart path called _compute_mobile_portfolio_summary — the "
            "ABCT-MOBILE-PERF contract is cache-only override")

    monkeypatch.setattr(mobile, "_compute_mobile_portfolio_summary",
                        must_not_compute)

    async def fake_unified(user_id, range="1w", by_chain=None):
        return {"data": _chart_points(),
                "coverage": {"oldest_date": "2026-11-02", "newest_date": "2026-11-03",
                             "total_days": 2}}

    monkeypatch.setattr(portfolio, "get_unified_chart", fake_unified)
    return store


async def test_chart_uses_cached_summary_for_live_total(monkeypatch, chart_env, clean_slots):
    chart_env.seed(mobile._summary_cache_key(USER, False),
                   {"total_value_usd": 555.0,
                    "breakdown": {"self_custody": {"value_usd": 500.0}}})

    result = await mobile.get_mobile_portfolio_history(
        user_id=USER, range="7d", slim=True)

    latest = result["chart_data"][-1]
    assert latest is not None
    assert latest["total_value_usd"] == 555.0  # header total, not DB snapshot


async def test_chart_without_cached_summary_stays_db_sourced_and_warms(
        monkeypatch, chart_env, clean_slots):
    result = await mobile.get_mobile_portfolio_history(
        user_id=USER, range="7d", slim=True)

    latest = result["chart_data"][-1]
    assert latest["total_value_usd"] == 101.0  # untouched DB point
    # and a background summary compute was scheduled for the next burst
    assert mobile._summary_cache_key(USER, False) in mobile._summary_refresh_tasks
    await _drain_summary_tasks()


# ---------------------------------------------------------------------------
# 3. 24h chart: bounded cold compute
# ---------------------------------------------------------------------------

async def test_24h_chart_cold_compute_is_bounded_and_deduped(monkeypatch, clean_slots):
    store = FakeCacheStore()
    monkeypatch.setattr(portfolio, "get_cache", store.get_cache)
    monkeypatch.setattr(portfolio, "get_stale_cache", store.get_stale_cache)
    monkeypatch.setattr(portfolio, "set_cache", store.set_cache)
    monkeypatch.setattr(portfolio, "CHART_24H_BOUNDED_WAIT_S", 0.4)

    async def fake_pref(user_id):
        return True

    monkeypatch.setattr(portfolio, "get_nft_inclusion_preference", fake_pref)

    key = f"portfolio_24h_hourly_v2_{USER}"

    async def slow_payload(user_id, include_nfts, cache_key):
        await asyncio.sleep(2.0)
        result = {"data": [{"date": "2026-11-03T10:00", "total_value": 1.0}],
                  "coverage": {"oldest_date": None, "newest_date": None, "total_days": 1}}
        await store.set_cache(cache_key, result)
        return result

    monkeypatch.setattr(portfolio, "_build_24h_hourly_payload", slow_payload)

    t0 = time.monotonic()
    first = await portfolio.get_24h_hourly_chart(user_id=USER, refresh=False)
    elapsed = time.monotonic() - t0
    assert elapsed < 1.5, f"cold 24h chart blocked {elapsed:.2f}s inline"
    assert first == {"data": [], "coverage": {"oldest_date": None,
                                              "newest_date": None, "total_days": 0}}
    assert key in portfolio._24h_compute_tasks  # deduped slot still working

    assert await _wait_until(lambda: not portfolio._24h_compute_tasks)

    second = await portfolio.get_24h_hourly_chart(user_id=USER, refresh=False)
    assert second["data"][0]["total_value"] == 1.0  # served from the warmed row


# ---------------------------------------------------------------------------
# 4. Alchemy 429 backoff
# ---------------------------------------------------------------------------

async def test_alchemy_429_sets_no_http_cooldown(monkeypatch):
    import services.ethereum_nft as eth_nft

    svc = eth_nft.EthereumNFTService()
    calls = {"n": 0}

    class FakeResponse:
        status_code = 429
        text = "rate limited"
        headers = {"Retry-After": "45"}

    class FakeClient:
        async def get(self, *a, **k):
            calls["n"] += 1
            return FakeResponse()

    monkeypatch.setattr(eth_nft, "get_client", lambda *a, **k: FakeClient())
    async def fake_key():
        return "k"
    async def fake_configured():
        return True
    monkeypatch.setattr(svc, "get_api_key", fake_key)
    monkeypatch.setattr(svc, "is_configured", fake_configured)

    assert await svc.get_nfts_for_owner("0xabc") is None
    assert calls["n"] == 1
    assert svc._cooldown_until > time.monotonic()

    # Inside the cooldown: None again, and NO further HTTP call.
    assert await svc.get_nfts_for_owner("0xabc") is None
    assert await svc.get_nfts_for_owner("0xdef") is None
    assert calls["n"] == 1

    # Cooldown expiry resumes calls.
    svc._cooldown_until = time.monotonic() - 1
    assert await svc.get_nfts_for_owner("0xabc") is None
    assert calls["n"] == 2


async def test_alchemy_429_respects_retry_after_clamp(monkeypatch):
    import services.ethereum_nft as eth_nft

    svc = eth_nft.EthereumNFTService()

    class FakeResponse:
        status_code = 429
        text = ""
        headers = {"Retry-After": "99999"}  # absurd — must clamp to 300

    class FakeClient:
        async def get(self, *a, **k):
            return FakeResponse()

    monkeypatch.setattr(eth_nft, "get_client", lambda *a, **k: FakeClient())
    async def fake_key():
        return "k"
    async def fake_configured():
        return True
    monkeypatch.setattr(svc, "get_api_key", fake_key)
    monkeypatch.setattr(svc, "is_configured", fake_configured)

    await svc.get_nfts_for_owner("0xabc")
    delta = svc._cooldown_until - time.monotonic()
    assert 290.0 <= delta <= 300.0


# ---------------------------------------------------------------------------
# 5. Scheduler no-provider warning throttle
# ---------------------------------------------------------------------------

async def test_no_provider_warning_throttled(caplog):
    from engine.scheduler import scheduler as sched

    sched._no_provider_warn_at.clear()
    with caplog.at_level("WARNING", logger="engine.scheduler.scheduler"):
        for _ in range(5):
            sched._warn_no_provider("cardano:normalize")
    warnings = [r for r in caplog.records
                if r.levelname == "WARNING" and "cardano:normalize" in r.message]
    assert len(warnings) == 1

    # After the window a new warning is allowed.
    sched._no_provider_warn_at["cardano:normalize"] -= sched.NO_PROVIDER_WARN_INTERVAL_S + 1
    caplog.clear()
    with caplog.at_level("WARNING", logger="engine.scheduler.scheduler"):
        sched._warn_no_provider("cardano:normalize")
    assert any(r.levelname == "WARNING" for r in caplog.records)
    sched._no_provider_warn_at.clear()
