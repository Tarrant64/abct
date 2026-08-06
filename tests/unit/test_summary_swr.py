"""
Unit tests for the /portfolio/summary stale-while-revalidate scheduler
(DASHBOARD-2): _schedule_summary_refresh must run one background recompute
per cache key at a time, always with refresh=False, clean up after itself
(success or failure), and allow rescheduling once finished.

These tests fake the compute function and do NOT require a running server.
"""

import asyncio
import os
import sys

# Add backend to sys.path so imports work
BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import routers.mobile as mobile  # noqa: E402


async def _wait_until(cond, timeout=2.0):
    for _ in range(int(timeout / 0.01)):
        if cond():
            return True
        await asyncio.sleep(0.01)
    return cond()


async def test_swr_schedules_one_refresh_and_dedupes(monkeypatch):
    calls = []
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_compute(user_id, refresh, include_sparklines):
        calls.append((user_id, refresh, include_sparklines))
        started.set()
        await release.wait()

    monkeypatch.setattr(mobile, "_compute_mobile_portfolio_summary", fake_compute)

    mobile._schedule_summary_refresh("swr_test_key", 7, True)
    mobile._schedule_summary_refresh("swr_test_key", 7, True)  # in-flight: no-op
    await asyncio.wait_for(started.wait(), timeout=2.0)
    assert calls == [(7, False, True)]  # one task; background never force-refreshes
    assert "swr_test_key" in mobile._summary_refresh_tasks

    release.set()
    assert await _wait_until(lambda: "swr_test_key" not in mobile._summary_refresh_tasks)

    # After completion the key can be scheduled again
    started.clear()
    release.set()
    mobile._schedule_summary_refresh("swr_test_key", 7, False)
    await asyncio.wait_for(started.wait(), timeout=2.0)
    assert calls[-1] == (7, False, False)
    assert await _wait_until(lambda: "swr_test_key" not in mobile._summary_refresh_tasks)


async def test_swr_cleans_up_on_compute_failure(monkeypatch):
    async def failing_compute(user_id, refresh, include_sparklines):
        raise RuntimeError("upstream exploded")

    monkeypatch.setattr(mobile, "_compute_mobile_portfolio_summary", failing_compute)

    mobile._schedule_summary_refresh("swr_fail_key", 7, True)
    assert await _wait_until(lambda: "swr_fail_key" not in mobile._summary_refresh_tasks)


async def test_swr_keys_are_independent(monkeypatch):
    running = set()
    release = asyncio.Event()

    async def fake_compute(user_id, refresh, include_sparklines):
        running.add(user_id)
        await release.wait()

    monkeypatch.setattr(mobile, "_compute_mobile_portfolio_summary", fake_compute)

    mobile._schedule_summary_refresh("swr_key_a", 1, True)
    mobile._schedule_summary_refresh("swr_key_b", 2, True)
    assert await _wait_until(lambda: running == {1, 2})
    release.set()
    assert await _wait_until(lambda: not mobile._summary_refresh_tasks)
