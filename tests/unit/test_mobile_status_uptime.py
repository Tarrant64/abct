"""
GET /api/mobile/status shipped `"uptime_seconds": 0` forever (a lying
placeholder). NAT-PRROUTE 2026-10-28 computes it from the module's process
start marker, so the mobile app's diagnostics screen shows real uptime.

Offline per tests/conftest.py: opt into `offline_stubs` and import the router
inside the test (no fastapi/httpx/aiosqlite needed at the boundary).
"""

import asyncio
import os
import sys
import time

import pytest

pytestmark = pytest.mark.usefixtures("offline_stubs")

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def _status():
    import routers.mobile as mobile

    return mobile, asyncio.run(mobile.get_mobile_api_status())


def test_uptime_is_a_real_nonnegative_int():
    _mobile, res = _status()
    assert isinstance(res["uptime_seconds"], int)
    assert res["uptime_seconds"] >= 0


def test_uptime_tracks_process_start_marker():
    mobile, _ = _status()
    original = mobile._PROCESS_START_TIME
    try:
        mobile._PROCESS_START_TIME = time.time() - 3600
        _, res = _status()
        assert 3595 <= res["uptime_seconds"] <= 3605
        # A clock skew that puts the marker in the future must clamp to 0,
        # never emit a negative uptime.
        mobile._PROCESS_START_TIME = time.time() + 10_000
        _, res = _status()
        assert res["uptime_seconds"] == 0
    finally:
        mobile._PROCESS_START_TIME = original


def test_status_shape_unchanged():
    # The mobile app reads these keys; the fix must not reshape the payload.
    _, res = _status()
    for key in ("status", "version", "build", "uptime_seconds", "services",
                "rate_limits", "server_time"):
        assert key in res
