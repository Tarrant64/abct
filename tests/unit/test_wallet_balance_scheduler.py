"""
Regression tests for ABCT-BGSYNC-20260919 (wallet balance background sync).

Mocks every provider call (_refresh_wallet_balance is monkeypatched, never
the real chain services) and makes no live network calls. Exercises the
scheduler against a real temporary SQLite file so the bucket-selection SQL,
the recency skip filter, and the cross-process advisory lock are all
genuinely exercised, not just asserted against in-memory fakes.
"""

import asyncio
import os
import sqlite3
import sys
from datetime import datetime, timedelta

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402
import routers.wallets as wallets_router  # noqa: E402
from services.wallet_balance_scheduler import WalletBalanceSchedulerService  # noqa: E402

USER_ID = 1
BUCKET_COUNT = 60


def _make_scheduler_db(tmp_path):
    """A minimal real SQLite file with wallets/balances/scheduler_locks --
    just what the scheduler's queries touch."""
    db_path = str(tmp_path / "test_bgsync.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE wallets (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            address TEXT NOT NULL,
            blockchain TEXT NOT NULL,
            label TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            amount TEXT NOT NULL,
            unit TEXT NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE scheduler_locks (
            lock_name TEXT PRIMARY KEY,
            holder TEXT NOT NULL,
            acquired_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    return db_path


def _insert_wallet(db_path, wallet_id, blockchain="cardano", address=None):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO wallets (id, user_id, address, blockchain, label) VALUES (?, ?, ?, ?, ?)",
        (wallet_id, USER_ID, address or f"addr{wallet_id}", blockchain, f"W{wallet_id}"),
    )
    conn.commit()
    conn.close()


def _insert_balance(db_path, wallet_id, updated_at):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO balances (wallet_id, user_id, amount, unit, updated_at) VALUES (?, ?, ?, ?, ?)",
        (wallet_id, USER_ID, "1.0", "ADA", updated_at),
    )
    conn.commit()
    conn.close()


def _new_scheduler(monkeypatch, enabled=True):
    monkeypatch.setattr("services.wallet_balance_scheduler.WALLET_BGSYNC_BUCKET_COUNT", BUCKET_COUNT)
    monkeypatch.setattr("services.wallet_balance_scheduler.WALLET_BGSYNC_SKIP_RECENT_MINUTES", 5)
    monkeypatch.setattr("services.wallet_balance_scheduler.WALLET_BGSYNC_DISPATCH_DELAY_SECONDS", 0.0)
    monkeypatch.setattr("services.wallet_balance_scheduler.WALLET_BGSYNC_LOCK_TTL_MINUTES", 3)
    svc = WalletBalanceSchedulerService()
    svc.enabled = enabled
    return svc


@pytest.mark.asyncio
async def test_skips_wallet_touched_in_last_5_minutes(monkeypatch, tmp_path):
    db_path = _make_scheduler_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)

    bucket = datetime.now().minute % BUCKET_COUNT
    fresh_wallet_id = bucket           # will be skipped: refreshed 1 min ago
    stale_wallet_id = bucket + BUCKET_COUNT  # will be processed: never refreshed
    _insert_wallet(db_path, fresh_wallet_id)
    _insert_wallet(db_path, stale_wallet_id)
    _insert_balance(db_path, fresh_wallet_id, datetime.now() - timedelta(minutes=1))
    # stale_wallet_id has no balances row at all -- always due

    calls = []

    async def fake_refresh(wallet):
        calls.append(wallet["id"])
        return {"success": True}

    monkeypatch.setattr(wallets_router, "_refresh_wallet_balance", fake_refresh)

    svc = _new_scheduler(monkeypatch)
    await svc.run_cycle()

    assert calls == [stale_wallet_id]
    assert svc.stats["last_attempted"] == 1
    assert svc.stats["last_skipped_recent"] == 1


@pytest.mark.asyncio
async def test_failing_wallet_does_not_abort_cycle(monkeypatch, tmp_path):
    db_path = _make_scheduler_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)

    bucket = datetime.now().minute % BUCKET_COUNT
    ids = [bucket, bucket + BUCKET_COUNT, bucket + 2 * BUCKET_COUNT]
    for wid in ids:
        _insert_wallet(db_path, wid)

    calls = []

    async def flaky_refresh(wallet):
        calls.append(wallet["id"])
        if wallet["id"] == ids[1]:
            raise RuntimeError("simulated RPC timeout")
        return {"success": True}

    monkeypatch.setattr(wallets_router, "_refresh_wallet_balance", flaky_refresh)

    svc = _new_scheduler(monkeypatch)
    await svc.run_cycle()

    # All three attempted despite the middle one raising -- the loop continued.
    assert calls == ids
    assert svc.stats["last_attempted"] == 3
    assert svc.stats["last_succeeded"] == 2
    assert svc.stats["last_failed"] == 1


@pytest.mark.asyncio
async def test_stagger_distributes_work_across_buckets(monkeypatch, tmp_path):
    db_path = _make_scheduler_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)

    # Two full "rows" of wallets across every bucket: ids 0..119 with
    # bucket_count=60 puts exactly two wallets in each bucket (i and i+60).
    for wid in range(2 * BUCKET_COUNT):
        _insert_wallet(db_path, wid)

    bucket_0 = await database.get_wallets_due_for_bgsync(0, BUCKET_COUNT, skip_recent_minutes=5)
    bucket_1 = await database.get_wallets_due_for_bgsync(1, BUCKET_COUNT, skip_recent_minutes=5)

    assert sorted(w["id"] for w in bucket_0) == [0, BUCKET_COUNT]
    assert sorted(w["id"] for w in bucket_1) == [1, BUCKET_COUNT + 1]
    # Not everything landed in one bucket.
    assert set(w["id"] for w in bucket_0).isdisjoint(w["id"] for w in bucket_1)


@pytest.mark.asyncio
async def test_kill_switch_disables_scheduler(monkeypatch, tmp_path):
    db_path = _make_scheduler_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)

    svc = _new_scheduler(monkeypatch, enabled=False)
    await svc.start()

    assert svc.scheduler is None, "kill switch must prevent the scheduler from starting at all"


@pytest.mark.asyncio
async def test_kill_switch_enabled_does_start(monkeypatch, tmp_path):
    db_path = _make_scheduler_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)

    svc = _new_scheduler(monkeypatch, enabled=True)
    await svc.start()
    try:
        assert svc.scheduler is not None
    finally:
        await svc.stop()


@pytest.mark.asyncio
async def test_lock_prevents_concurrent_duplicate_cycles(monkeypatch, tmp_path):
    db_path = _make_scheduler_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)

    bucket = datetime.now().minute % BUCKET_COUNT
    _insert_wallet(db_path, bucket)

    calls = []
    release_gate = asyncio.Event()

    async def slow_refresh(wallet):
        calls.append(wallet["id"])
        # Hold the "cycle" open long enough for a concurrent second cycle
        # to attempt (and fail) to acquire the same lock.
        await release_gate.wait()
        return {"success": True}

    monkeypatch.setattr(wallets_router, "_refresh_wallet_balance", slow_refresh)

    svc_a = _new_scheduler(monkeypatch)
    svc_b = _new_scheduler(monkeypatch)
    assert svc_a._holder != svc_b._holder

    async def run_a():
        await svc_a.run_cycle()

    async def run_b_after_a_has_the_lock():
        # Give svc_a's run_cycle a chance to acquire the lock and reach the
        # blocked refresh call before svc_b tries.
        await asyncio.sleep(0.05)
        await svc_b.run_cycle()
        release_gate.set()

    await asyncio.gather(run_a(), run_b_after_a_has_the_lock())

    # svc_b must have been shut out entirely -- only svc_a's single wallet
    # call happened, not two.
    assert calls == [bucket]
    assert svc_b.stats["lock_skipped_cycles"] == 1
    assert svc_a.stats["last_attempted"] == 1
