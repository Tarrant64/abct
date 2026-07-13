"""
Unit tests for the /portfolio/summary stale-age cap and SWR-slot timeout
(PRICE-1 echo-loop fix).

Without the cap, a client whose visits are sparse — the phone is the only
consumer of its include_sparklines=false cache variant — was ALWAYS answered
with the payload computed during its previous visit: the SWR background
recompute landed after the response and nothing ever fetched it. Covered:

- stale row past SUMMARY_STALE_MAX_AGE_S → synchronous fresh compute, no echo,
  no SWR task;
- stale row within the bound → SWR behavior unchanged (echo served, recompute
  scheduled);
- missing/malformed expires_at → treated as too old (synchronous);
- a hung background recompute is cancelled after SUMMARY_REFRESH_TIMEOUT_S and
  frees its single-flight slot.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta

# Add backend to sys.path so imports work
BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import routers.mobile as mobile  # noqa: E402

from tests.unit.test_summary_cache_variants import (  # noqa: E402
    _install_fake_cache,
    _stub_compute_upstreams,
    _wait_until,
)

USER = 7


def _expired_ago(seconds: float) -> str:
    return (datetime.now() - timedelta(seconds=seconds)).isoformat()


async def test_old_stale_row_computes_synchronously_instead_of_echoing(monkeypatch):
    cache = _install_fake_cache(monkeypatch)
    _stub_compute_upstreams(monkeypatch)

    key = mobile._summary_cache_key(USER, False)
    echo = {"total_value_usd": 13779.17, "variant": "previous-visit"}
    cache.seed(key, echo, fresh=False,
               expires_at=_expired_ago(mobile.SUMMARY_STALE_MAX_AGE_S + 1))

    served = await mobile.get_mobile_portfolio_summary(
        user_id=USER, refresh=False, include_sparklines=False)

    assert served != echo  # fresh synchronous compute, not the echo
    assert served["from_cache"] is False
    assert not mobile._summary_refresh_tasks  # no background task needed
    assert cache.store[key] == served  # row rewritten for the next request


async def test_young_stale_row_keeps_swr_path(monkeypatch):
    cache = _install_fake_cache(monkeypatch)
    _stub_compute_upstreams(monkeypatch)

    key = mobile._summary_cache_key(USER, False)
    echo = {"total_value_usd": 111, "variant": "just-expired"}
    cache.seed(key, echo, fresh=False,
               expires_at=_expired_ago(mobile.SUMMARY_STALE_MAX_AGE_S - 30))

    served = await mobile.get_mobile_portfolio_summary(
        user_id=USER, refresh=False, include_sparklines=False)

    assert served == echo  # young stale rows still serve instantly
    assert key in mobile._summary_refresh_tasks  # with a recompute behind them
    assert await _wait_until(lambda: not mobile._summary_refresh_tasks)
    assert cache.store[key] != echo  # recompute landed


async def test_missing_or_malformed_expiry_is_treated_as_too_old(monkeypatch):
    assert mobile._stale_summary_servable(None) is False
    assert mobile._stale_summary_servable("") is False
    assert mobile._stale_summary_servable("not-a-timestamp") is False

    cache = _install_fake_cache(monkeypatch)
    _stub_compute_upstreams(monkeypatch)
    key = mobile._summary_cache_key(USER, True)
    echo = {"total_value_usd": 222, "variant": "no-expiry"}
    cache.seed(key, echo, fresh=False, expires_at="not-a-timestamp")

    served = await mobile.get_mobile_portfolio_summary(
        user_id=USER, refresh=False, include_sparklines=True)
    assert served != echo
    assert not mobile._summary_refresh_tasks


async def test_hung_background_recompute_times_out_and_frees_slot(monkeypatch):
    monkeypatch.setattr(mobile, "SUMMARY_REFRESH_TIMEOUT_S", 0.05)
    cancelled = asyncio.Event()

    async def hung_compute(user_id, refresh, include_sparklines):
        try:
            await asyncio.Event().wait()  # never completes on its own
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(mobile, "_compute_mobile_portfolio_summary", hung_compute)

    mobile._schedule_summary_refresh("stale_cap_hung_key", USER, False)
    assert "stale_cap_hung_key" in mobile._summary_refresh_tasks

    assert await _wait_until(
        lambda: "stale_cap_hung_key" not in mobile._summary_refresh_tasks)
    assert await _wait_until(cancelled.is_set)  # hung work cancelled, not leaked

    # The freed slot accepts a new recompute
    ran = asyncio.Event()

    async def quick_compute(user_id, refresh, include_sparklines):
        ran.set()

    monkeypatch.setattr(mobile, "_compute_mobile_portfolio_summary", quick_compute)
    mobile._schedule_summary_refresh("stale_cap_hung_key", USER, False)
    await asyncio.wait_for(ran.wait(), timeout=2.0)
    assert await _wait_until(
        lambda: "stale_cap_hung_key" not in mobile._summary_refresh_tasks)
