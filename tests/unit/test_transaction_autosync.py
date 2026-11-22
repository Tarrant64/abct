"""Transaction history must be refreshed by a scheduled loop, not only by a manual web action."""

import asyncio
import os
import sys

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from services import transaction_autosync as ta  # noqa: E402


def test_syncs_real_users_skips_demo_and_isolates_failures():
    calls = []

    async def users():
        return [{"id": 1, "is_demo": 0}, {"id": 2, "is_demo": 1}, {"id": 3, "is_demo": 0}, {"id": 4, "is_demo": 0}]

    async def fetch(uid, days):
        calls.append((uid, days))
        if uid == 3:
            raise RuntimeError("provider down")
        return {"cardano": 2, "bitcoin": 1}

    out = asyncio.run(ta.sync_all_users(users, fetch))
    assert [c[0] for c in calls] == [1, 3, 4]
    assert out == {1: 3, 4: 3}
    assert all(d == ta.SYNC_DAYS for _, d in calls)


def test_env_controls(monkeypatch):
    monkeypatch.delenv("ABCT_TX_AUTOSYNC", raising=False)
    assert ta.autosync_enabled()
    monkeypatch.setenv("ABCT_TX_AUTOSYNC", "off")
    assert not ta.autosync_enabled()
    monkeypatch.setenv("ABCT_TX_AUTOSYNC_INTERVAL_MIN", "1")
    assert ta.interval_seconds() == 300
    monkeypatch.setenv("ABCT_TX_AUTOSYNC_INTERVAL_MIN", "junk")
    assert ta.interval_seconds() == 3600


def test_wired_into_lifespan():
    src = open(os.path.join(BACKEND_DIR, "main.py")).read()
    assert "periodic_transaction_sync" in src
