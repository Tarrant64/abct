"""
P3-FIX2 contract tests: non-blocking staking reads and prompt async refresh.

Deploy-5 evidence: a paced full-account rescan structurally cannot finish
inside the proxy's 60 s window, and reads queueing behind in-flight scans
went 4.4 s → 504. The route must NEVER block on a rescan: no-refresh reads
always serve the cache (fresh, stale, or an empty valid payload), and
refresh=true answers promptly with the best current data plus
refreshing/data_as_of while the compute runs deduped in the background.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import routers.defi as defi_router  # noqa: E402
from routers.defi import get_staking_positions  # noqa: E402

ADDRESS = "addr1q9phspv20nxtestonly"

FULL_ROW = {
    "address": ADDRESS,
    "protocols": {"Indigo": {"staked": [{"token": "INDY", "amount": 8670.38}]}},
    "total_positions": 1,
}


async def _bounded(coro, seconds=1.0):
    """The route must answer without ever awaiting a scan — enforce it."""
    return await asyncio.wait_for(coro, timeout=seconds)


@pytest.fixture
async def env(monkeypatch):
    """Route wired to a controllable cache and a compute that HANGS until
    released — any accidental read/compute coupling times the test out."""
    state = {
        "fresh": None,
        "stale": None,
        "compute_calls": 0,
        "release": asyncio.Event(),
    }

    async def fake_get_cache(key, user_id=None):
        return dict(state["fresh"]) if state["fresh"] else None

    async def fake_get_stale_cache(key, user_id=None):
        if state["stale"]:
            return dict(state["stale"]), "2026-07-13T00:00:00"
        return None, None

    monkeypatch.setattr(defi_router, "get_cache", fake_get_cache)
    monkeypatch.setattr(defi_router, "get_stale_cache", fake_get_stale_cache)

    async def fake_username(user_id):
        return "admin"

    async def fake_is_demo(username):
        return False

    monkeypatch.setattr(defi_router, "get_username_by_user_id", fake_username)
    monkeypatch.setattr(defi_router, "is_demo_user", fake_is_demo)

    async def slow_compute(address, user_id):
        state["compute_calls"] += 1
        await state["release"].wait()
        return {"address": address, "protocols": {}}

    monkeypatch.setattr(defi_router, "_compute_staking_positions", slow_compute)

    defi_router._staking_refresh_tasks.clear()
    defi_router._staking_scan_completions.clear()
    yield state
    # Unblock and drain any scheduled job INSIDE this test's event loop so
    # no background task leaks past loop teardown
    state["release"].set()
    for task in list(defi_router._staking_refresh_tasks.values()):
        try:
            await asyncio.wait_for(task, timeout=1)
        except Exception:
            pass
    defi_router._staking_refresh_tasks.clear()
    defi_router._staking_scan_completions.clear()


async def test_read_with_fresh_cache_never_touches_compute(env):
    env["fresh"] = dict(FULL_ROW)

    out = await _bounded(get_staking_positions(ADDRESS, refresh=False, user_id=1))

    assert out["from_cache"] is True
    assert out["protocols"]["Indigo"]["staked"]
    assert env["compute_calls"] == 0
    assert not defi_router._staking_refresh_tasks


async def test_cold_read_returns_immediately_never_inline_computes(env):
    """THE deploy-5 regression: a cold read must not queue behind in-flight
    scans. With the compute hung forever, the read still answers instantly
    with a schema-valid empty payload and schedules the fill."""
    out = await _bounded(get_staking_positions(ADDRESS, refresh=False, user_id=1))

    assert out["protocols"] == {}
    assert out["refreshing"] is True
    assert out["data_as_of"] is None
    assert defi_router._staking_refresh_tasks  # background fill scheduled
    await asyncio.sleep(0)
    assert env["compute_calls"] == 1  # exactly one, in the background


async def test_stale_read_serves_stale_immediately(env):
    env["stale"] = dict(FULL_ROW)

    out = await _bounded(get_staking_positions(ADDRESS, refresh=False, user_id=1))

    assert out["stale"] is True
    assert out["protocols"]["Indigo"]["staked"]
    assert defi_router._staking_refresh_tasks


async def test_refresh_returns_promptly_with_best_data(env):
    """Async refresh contract: 200 with the same schema carrying the best
    current data + refreshing:true, while the paced rescan continues."""
    old = dict(FULL_ROW)
    old["cached_at"] = (datetime.now() - timedelta(hours=3)).isoformat()
    env["fresh"] = old

    out = await _bounded(get_staking_positions(ADDRESS, refresh=True, user_id=1))

    assert out["refreshing"] is True
    assert out["data_as_of"] == old["cached_at"]
    assert out["from_cache"] is True
    assert out["protocols"]["Indigo"]["staked"]  # best data, not empty
    assert defi_router._staking_refresh_tasks
    await asyncio.sleep(0)
    assert env["compute_calls"] == 1


async def test_refresh_with_stale_only_serves_stale_refreshing(env):
    env["stale"] = dict(FULL_ROW)

    out = await _bounded(get_staking_positions(ADDRESS, refresh=True, user_id=1))

    assert out["refreshing"] is True
    assert out["stale"] is True
    assert out["protocols"]["Indigo"]["staked"]


async def test_refresh_cold_serves_empty_refreshing(env):
    out = await _bounded(get_staking_positions(ADDRESS, refresh=True, user_id=1))

    assert out["refreshing"] is True
    assert out["protocols"] == {}
    assert defi_router._staking_refresh_tasks


async def test_second_refresh_joins_inflight_scan(env):
    """Dedupe: a second hard pull during an in-flight rescan must not start
    a second scan."""
    out1 = await _bounded(get_staking_positions(ADDRESS, refresh=True, user_id=1))
    await asyncio.sleep(0)
    out2 = await _bounded(get_staking_positions(ADDRESS, refresh=True, user_id=1))
    await asyncio.sleep(0)

    assert out1["refreshing"] and out2["refreshing"]
    assert env["compute_calls"] == 1
    assert len(defi_router._staking_refresh_tasks) == 1


async def test_background_completion_clears_slot_and_cooldown_holds(env):
    await _bounded(get_staking_positions(ADDRESS, refresh=True, user_id=1))
    await asyncio.sleep(0)
    assert env["compute_calls"] == 1

    env["release"].set()
    for _ in range(20):
        if not defi_router._staking_refresh_tasks:
            break
        await asyncio.sleep(0.01)
    assert not defi_router._staking_refresh_tasks

    # P3-FIX3: a wallet whose scan JUST completed is under the completion
    # cooldown — another refresh must not rescan it (deploy-6 defect iv)
    env["release"] = asyncio.Event()
    await _bounded(get_staking_positions(ADDRESS, refresh=True, user_id=1))
    await asyncio.sleep(0)
    assert env["compute_calls"] == 1  # cooldown held
    assert not defi_router._staking_refresh_tasks

    # After the cooldown expires, rescans work again
    import time as _t
    key = f"1:staking_positions_{ADDRESS}"
    defi_router._staking_scan_completions[key] = (
        _t.monotonic() - defi_router.STAKING_RESCAN_COOLDOWN_S - 1
    )
    await _bounded(get_staking_positions(ADDRESS, refresh=True, user_id=1))
    await asyncio.sleep(0)
    assert env["compute_calls"] == 2
    env["release"].set()


async def test_refresh_after_recent_scan_serves_fresh_no_rescan(env):
    """A scan that completed <60s ago is fresh enough: serve it with
    refreshing:false and do NOT schedule another rescan."""
    fresh = dict(FULL_ROW)
    fresh["cached_at"] = datetime.now().isoformat()
    env["fresh"] = fresh

    out = await _bounded(get_staking_positions(ADDRESS, refresh=True, user_id=1))

    assert out["refreshing"] is False
    assert out["data_as_of"] == fresh["cached_at"]
    assert out["protocols"]["Indigo"]["staked"]
    assert env["compute_calls"] == 0
    assert not defi_router._staking_refresh_tasks
