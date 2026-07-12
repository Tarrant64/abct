"""
P3b infrastructure tests: stale-hit SWR revalidation, cache-cleanup grace
window, Blockfrost 429 pacing, wallet-context append cap, and the Indigo
adapter delegation (dead /api/v1 paths removed).
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
import routers.defi as defi_router  # noqa: E402
import services.defi as defi_module  # noqa: E402
import services.http_client as http_client  # noqa: E402
from routers.defi import get_staking_positions  # noqa: E402

ADDRESS = "addr1q9phspv20nxtestonly"

STALE_ROW = {
    "address": ADDRESS,
    "protocols": {"Iagon": {"staked": [{"token": "IAG", "amount": 3858.0}]}},
    "total_positions": 1,
}


async def _wait_until(cond, timeout=2.0):
    for _ in range(int(timeout / 0.01)):
        if cond():
            return True
        await asyncio.sleep(0.01)
    return cond()


# ---------------------------------------------------------------------------
# Stale-hit SWR: background revalidation, deduped, refresh-free
# ---------------------------------------------------------------------------

@pytest.fixture
def swr_env(monkeypatch):
    calls = []
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_compute(address, user_id):
        calls.append((address, user_id))
        started.set()
        await release.wait()
        return {"address": address, "protocols": {}}

    monkeypatch.setattr(defi_router, "_compute_staking_positions", fake_compute)

    async def fake_get_cache(key, user_id=None):
        return None  # fresh row always misses

    async def fake_get_stale(key, user_id=None):
        return dict(STALE_ROW), "2026-07-13T00:00:00"

    monkeypatch.setattr(defi_router, "get_cache", fake_get_cache)
    monkeypatch.setattr(defi_router, "get_stale_cache", fake_get_stale)

    async def fake_username(user_id):
        return "admin"

    async def fake_is_demo(username):
        return False

    monkeypatch.setattr(defi_router, "get_username_by_user_id", fake_username)
    monkeypatch.setattr(defi_router, "is_demo_user", fake_is_demo)

    defi_router._staking_refresh_tasks.clear()
    return calls, started, release


async def test_stale_hit_serves_stale_and_revalidates_once(swr_env):
    calls, started, release = swr_env

    # Three concurrent stale hits — all get the stale row instantly
    outs = await asyncio.gather(*[
        get_staking_positions(ADDRESS, refresh=False, user_id=1)
        for _ in range(3)
    ])
    for out in outs:
        assert out["stale"] is True
        assert out["from_cache"] is True

    # Exactly ONE background recompute, without refresh semantics
    assert await _wait_until(lambda: len(calls) >= 1)
    await asyncio.sleep(0.05)
    assert calls == [(ADDRESS, 1)]

    # Finishing the job clears the in-flight slot so a later stale hit can
    # schedule again
    release.set()
    assert await _wait_until(lambda: not defi_router._staking_refresh_tasks)

    await get_staking_positions(ADDRESS, refresh=False, user_id=1)
    assert await _wait_until(lambda: len(calls) == 2)


async def test_stale_hits_for_different_users_schedule_separately(swr_env):
    calls, started, release = swr_env

    await get_staking_positions(ADDRESS, refresh=False, user_id=1)
    await get_staking_positions(ADDRESS, refresh=False, user_id=2)

    assert await _wait_until(lambda: len(calls) == 2)
    assert sorted(c[1] for c in calls) == [1, 2]
    release.set()


# ---------------------------------------------------------------------------
# cleanup_expired_cache: grace window + localtime comparison
# ---------------------------------------------------------------------------

async def test_cleanup_grace_window_spares_recent_stale_rows(monkeypatch, tmp_path):
    db_path = tmp_path / "portfolio.db"
    db = sqlite3.connect(db_path)
    db.execute(
        "CREATE TABLE cache (user_id INTEGER, key TEXT, value TEXT,"
        " expires_at TEXT, PRIMARY KEY (user_id, key))"
    )
    now = datetime.now()  # set_cache writes LOCAL time isoformat
    rows = [
        (1, "fresh", "{}", (now + timedelta(hours=1)).isoformat()),
        (1, "stale_1d", "{}", (now - timedelta(days=1)).isoformat()),
        (1, "stale_6d", "{}", (now - timedelta(days=6)).isoformat()),
        (1, "stale_8d", "{}", (now - timedelta(days=8)).isoformat()),
        (1, "stale_30d", "{}", (now - timedelta(days=30)).isoformat()),
    ]
    db.executemany("INSERT INTO cache VALUES (?, ?, ?, ?)", rows)
    db.commit()
    db.close()

    monkeypatch.setattr(database, "DATABASE_PATH", db_path)

    deleted = await database.cleanup_expired_cache()

    assert deleted == 2  # only the >7-day-expired rows

    db = sqlite3.connect(db_path)
    remaining = sorted(r[0] for r in db.execute("SELECT key FROM cache"))
    db.close()
    # Recently-expired rows survive: they are the get_stale_cache fallback
    # and the staking guard's baseline
    assert remaining == ["fresh", "stale_1d", "stale_6d"]


# ---------------------------------------------------------------------------
# Blockfrost 429 pacing
# ---------------------------------------------------------------------------

class _Resp:
    def __init__(self, status_code):
        self.status_code = status_code


class _FakeTime:
    """Virtual clock: monkeypatched in as _bf_monotonic/_bf_sleep so pacing
    math runs deterministically with no wall-clock waits."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    async def sleep(self, d):
        self.sleeps.append(d)
        self.now += max(d, 0)


@pytest.fixture
def bf_env(monkeypatch):
    """Fresh bucket + virtual clock for pacing tests."""
    ft = _FakeTime()
    monkeypatch.setattr(http_client, "_bf_monotonic", ft.monotonic)
    monkeypatch.setattr(http_client, "_bf_sleep", ft.sleep)
    monkeypatch.setattr(http_client, "_blockfrost_bucket", http_client._TokenBucket(
        http_client._BLOCKFROST_BUCKET_CAPACITY,
        http_client._BLOCKFROST_BUCKET_REFILL,
    ))
    return ft


async def test_blockfrost_429_paced_retry(monkeypatch, bf_env):
    attempts = []

    async def fake_once(path, **kwargs):
        attempts.append(path)
        return _Resp(429 if len(attempts) < 3 else 200)

    monkeypatch.setattr(http_client, "_blockfrost_fetch_once", fake_once)

    before = http_client.blockfrost_stats()
    resp = await http_client.blockfrost_fetch("/test/path")
    after = http_client.blockfrost_stats()

    assert resp.status_code == 200
    assert len(attempts) == 3  # two 429s, then success
    # Backoff sleeps happened (doubling), plus bucket refill waits after the
    # 429 penalty emptied the bucket
    assert 1.0 in bf_env.sleeps and 2.0 in bf_env.sleeps
    assert after["requests"] - before["requests"] == 3
    assert after["throttled_429"] - before["throttled_429"] == 2


async def test_blockfrost_429_gives_up_after_retries(monkeypatch, bf_env):
    async def always_429(path, **kwargs):
        return _Resp(429)

    monkeypatch.setattr(http_client, "_blockfrost_fetch_once", always_429)

    resp = await http_client.blockfrost_fetch("/test/path")
    assert resp.status_code == 429  # surfaced, caller's error handling applies


async def test_blockfrost_success_costs_one_request(monkeypatch, bf_env):
    async def ok(path, **kwargs):
        return _Resp(200)

    monkeypatch.setattr(http_client, "_blockfrost_fetch_once", ok)

    before = http_client.blockfrost_stats()
    resp = await http_client.blockfrost_fetch("/test/path")
    after = http_client.blockfrost_stats()

    assert resp.status_code == 200
    assert after["requests"] - before["requests"] == 1
    assert after["throttled_429"] == before["throttled_429"]
    assert bf_env.sleeps == []  # full bucket: no pacing delay


# ---------------------------------------------------------------------------
# Wallet-context append cap
# ---------------------------------------------------------------------------

async def test_context_append_cap(monkeypatch, caplog):
    import services.cardano as cardano_module

    monkeypatch.setattr(cardano_module, "_derive_stake_key_local",
                        lambda a: "stake1uCAPTEST")

    koios = [f"addr1koios{i}" for i in range(3)]
    appended = [f"addr1appended{i}" for i in range(100)]
    cached_ctx = {
        "address": koios[0],
        "stake_address": "stake1uCAPTEST",
        "addresses": koios + appended,
        "koios_addresses": koios,
        "payment_creds": [f"cred{i}" for i in range(103)],
        "resolved": True,
    }

    store = {(None, "wallet_context_stake1uCAPTEST"): cached_ctx}

    async def fake_get_cache(key, user_id=None):
        return store.get((user_id, key))

    set_calls = []

    async def fake_set_cache(key, value, ttl, user_id=None):
        set_calls.append(key)

    monkeypatch.setattr(database, "get_cache", fake_get_cache)
    monkeypatch.setattr(database, "set_cache", fake_set_cache)

    with caplog.at_level("WARNING"):
        ctx = await defi_module.defi_service.resolve_wallet_context("addr1qBRANDNEW")

    assert "addr1qBRANDNEW" not in ctx["addresses"]  # unmerged
    assert set_calls == []  # no cache growth
    assert any("append cap" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# Indigo adapter delegation (dead /api/v1 paths removed)
# ---------------------------------------------------------------------------

async def test_indigo_adapter_delegates_and_maps(monkeypatch):
    from services.defi_protocols.cardano.indigo import IndigoAdapter
    from services.defi_protocols.base_adapter import PositionType

    async def fake_staking(address, payment_creds=None):
        return {"protocol": "Indigo", "address": address,
                "positions": [{"staked_indy": 8670.38}],
                "total_staked_indy": 8670.383309, "position_count": 1}

    async def fake_cdps(address, payment_creds=None):
        return {"protocol": "Indigo", "address": address,
                "cdps": [{"asset": "iUSD", "collateral_ada": 2500.0,
                          "minted_amount": 750.0, "min_collateral_ratio": 150,
                          "output_hash": "abc"}],
                "total_collateral_ada": 2500.0, "cdp_count": 1}

    async def fake_sp(address):
        return None  # disabled

    monkeypatch.setattr(defi_module.defi_service, "get_indigo_staking", fake_staking)
    monkeypatch.setattr(defi_module.defi_service, "get_indigo_cdps", fake_cdps)
    monkeypatch.setattr(defi_module.defi_service, "get_indigo_stability_pool", fake_sp)

    adapter = IndigoAdapter()
    positions = await adapter.detect_positions(ADDRESS)

    assert len(positions) == 2
    staking = next(p for p in positions if p.position_type == PositionType.STAKING)
    assert staking.token_symbol == "INDY"
    assert staking.amount == pytest.approx(8670.383309)
    assert staking.extra["position_count"] == 1

    cdp = next(p for p in positions if p.position_type == PositionType.CDP)
    assert cdp.token_symbol == "iUSD"
    assert cdp.amount == pytest.approx(750.0)
    assert cdp.extra["collateral_ada"] == pytest.approx(2500.0)
    assert cdp.extra["min_collateral_ratio"] == 150


async def test_indigo_adapter_confirmed_empty_maps_to_no_positions(monkeypatch):
    from services.defi_protocols.cardano.indigo import IndigoAdapter

    async def empty_staking(address, payment_creds=None):
        return {"protocol": "Indigo", "positions": [], "total_staked_indy": 0,
                "position_count": 0, "confirmed_empty": True}

    async def empty_cdps(address, payment_creds=None):
        return {"protocol": "Indigo", "cdps": [], "total_collateral_ada": 0,
                "cdp_count": 0, "confirmed_empty": True}

    async def none_sp(address):
        return None

    monkeypatch.setattr(defi_module.defi_service, "get_indigo_staking", empty_staking)
    monkeypatch.setattr(defi_module.defi_service, "get_indigo_cdps", empty_cdps)
    monkeypatch.setattr(defi_module.defi_service, "get_indigo_stability_pool", none_sp)

    adapter = IndigoAdapter()
    assert await adapter.detect_positions(ADDRESS) == []
    # Legacy standalone methods keep their None-for-empty contract
    assert await adapter.get_cdp_positions(ADDRESS) is None


# The dead-Indigo-path grep test now lives in test_p3_fix.py
# (test_no_dead_indigo_path_literals_in_runtime_code) — the original here
# grepped a base-URL concatenation that could never match (vacuous).
