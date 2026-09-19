"""
Regression tests for ABCT-STAKE-REDISCOVERY-20260919.

Mocks cardano_service and _refresh_wallet_balance -- no live provider calls.
Exercises the real database.py functions (save_wallet, get_wallet_by_address,
the lock, the audit table) against a real temporary SQLite file, so the
actual discovery/add/idempotency logic is genuinely exercised.
"""

import asyncio
import os
import sqlite3
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402
import routers.wallets as wallets_router  # noqa: E402
import services.cardano as cardano_module  # noqa: E402
from services.stake_rediscovery_scheduler import StakeRediscoveryService  # noqa: E402

USER_ID = 1


def _make_test_db(tmp_path):
    db_path = str(tmp_path / "test_rediscovery.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            address TEXT NOT NULL,
            blockchain TEXT NOT NULL,
            label TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, address, blockchain)
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
    conn.execute("""
        CREATE TABLE stake_rediscovery_additions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            stake_address TEXT NOT NULL,
            address TEXT NOT NULL,
            wallet_id INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    return db_path


def _insert_wallet(db_path, address, user_id=USER_ID):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO wallets (user_id, address, blockchain, label) VALUES (?, ?, 'cardano', ?)",
        (user_id, address, "Known Wallet"),
    )
    conn.commit()
    conn.close()


def _new_service(monkeypatch, enabled=True):
    monkeypatch.setattr("services.stake_rediscovery_scheduler.STAKE_REDISCOVERY_DISPATCH_DELAY_SECONDS", 0.0)
    monkeypatch.setattr("services.stake_rediscovery_scheduler.STAKE_REDISCOVERY_LOCK_TTL_MINUTES", 120)
    svc = StakeRediscoveryService()
    svc.enabled = enabled
    return svc


@pytest.mark.asyncio
async def test_discovers_and_adds_new_address_under_registered_stake_key(tmp_path, monkeypatch):
    db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    _insert_wallet(db_path, "addr1_known")

    stake_calls = []
    listing_calls = []

    async def fake_get_stake_address(address):
        stake_calls.append(address)
        return "stake1abc"

    async def fake_get_addresses_from_stake(stake_address):
        listing_calls.append(stake_address)
        return ["addr1_known", "addr1_new"]

    async def fake_get_address_info(address):
        return {"balance_ada": 100.0, "native_assets": []}

    refreshed = []

    async def fake_refresh(wallet):
        refreshed.append(wallet["address"])
        return {"success": True}

    monkeypatch.setattr(cardano_module.cardano_service, "get_stake_address", fake_get_stake_address)
    monkeypatch.setattr(cardano_module.cardano_service, "get_addresses_from_stake", fake_get_addresses_from_stake)
    monkeypatch.setattr(cardano_module.cardano_service, "get_address_info", fake_get_address_info)
    monkeypatch.setattr(wallets_router, "_refresh_wallet_balance", fake_refresh)

    svc = _new_service(monkeypatch)
    await svc.run_cycle()

    assert stake_calls == ["addr1_known"]
    new_wallet = await database.get_wallet_by_address("addr1_new", "cardano", user_id=USER_ID)
    assert new_wallet is not None
    assert refreshed == ["addr1_new"]

    additions = await database.get_recent_stake_rediscovery_additions(USER_ID)
    assert len(additions) == 1
    assert additions[0]["address"] == "addr1_new"
    assert additions[0]["stake_address"] == "stake1abc"

    assert svc.stats["last_addresses_added"] == 1


@pytest.mark.asyncio
async def test_never_queries_an_unregistered_stake_key(tmp_path, monkeypatch):
    """Hard boundary: the only stake key ever queried must be one derived
    from a wallet the user already registered -- never an arbitrary one."""
    db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    _insert_wallet(db_path, "addr1_known")

    listing_calls = []

    async def fake_get_stake_address(address):
        return "stake1abc"

    async def fake_get_addresses_from_stake(stake_address):
        listing_calls.append(stake_address)
        return ["addr1_known"]  # nothing new

    monkeypatch.setattr(cardano_module.cardano_service, "get_stake_address", fake_get_stake_address)
    monkeypatch.setattr(cardano_module.cardano_service, "get_addresses_from_stake", fake_get_addresses_from_stake)

    svc = _new_service(monkeypatch)
    await svc.run_cycle()

    assert listing_calls == ["stake1abc"], "must only ever query stake keys derived from registered wallets"


@pytest.mark.asyncio
async def test_idempotent_second_run_does_not_duplicate(tmp_path, monkeypatch):
    db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    _insert_wallet(db_path, "addr1_known")

    async def fake_get_stake_address(address):
        return "stake1abc"

    async def fake_get_addresses_from_stake(stake_address):
        return ["addr1_known", "addr1_new"]

    info_calls = []

    async def fake_get_address_info(address):
        info_calls.append(address)
        return {"balance_ada": 100.0, "native_assets": []}

    async def fake_refresh(wallet):
        return {"success": True}

    monkeypatch.setattr(cardano_module.cardano_service, "get_stake_address", fake_get_stake_address)
    monkeypatch.setattr(cardano_module.cardano_service, "get_addresses_from_stake", fake_get_addresses_from_stake)
    monkeypatch.setattr(cardano_module.cardano_service, "get_address_info", fake_get_address_info)
    monkeypatch.setattr(wallets_router, "_refresh_wallet_balance", fake_refresh)

    svc = _new_service(monkeypatch)
    await svc.run_cycle()
    await svc.run_cycle()

    additions = await database.get_recent_stake_rediscovery_additions(USER_ID)
    assert len(additions) == 1, "second run must not create a duplicate addition record"
    assert info_calls == ["addr1_new"], "second run must not re-check a wallet it already knows about"


@pytest.mark.asyncio
async def test_kill_switch_disables_scheduler(tmp_path, monkeypatch):
    db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)

    svc = _new_service(monkeypatch, enabled=False)
    await svc.start()

    assert svc.scheduler is None


@pytest.mark.asyncio
async def test_failure_in_one_stake_key_does_not_abort_the_cycle(tmp_path, monkeypatch):
    db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    _insert_wallet(db_path, "addr1_bad")
    _insert_wallet(db_path, "addr1_good")

    async def fake_get_stake_address(address):
        return "stake1bad" if address == "addr1_bad" else "stake1good"

    async def fake_get_addresses_from_stake(stake_address):
        if stake_address == "stake1bad":
            raise RuntimeError("Blockfrost timeout")
        return ["addr1_good", "addr1_good_new"]

    async def fake_get_address_info(address):
        return {"balance_ada": 5.0, "native_assets": []}

    async def fake_refresh(wallet):
        return {"success": True}

    monkeypatch.setattr(cardano_module.cardano_service, "get_stake_address", fake_get_stake_address)
    monkeypatch.setattr(cardano_module.cardano_service, "get_addresses_from_stake", fake_get_addresses_from_stake)
    monkeypatch.setattr(cardano_module.cardano_service, "get_address_info", fake_get_address_info)
    monkeypatch.setattr(wallets_router, "_refresh_wallet_balance", fake_refresh)

    svc = _new_service(monkeypatch)
    await svc.run_cycle()

    # The bad stake key failed, but the good one was still processed.
    good_new = await database.get_wallet_by_address("addr1_good_new", "cardano", user_id=USER_ID)
    assert good_new is not None
    assert svc.stats["last_failed"] >= 1
    assert svc.stats["last_addresses_added"] == 1
