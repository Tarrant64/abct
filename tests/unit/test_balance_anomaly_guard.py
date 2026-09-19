"""
Regression tests for ABCT-BALANCE-GUARD-20260919.

Root cause this guards against: nothing compared a newly-fetched balance to
the previously stored one before overwriting it, so a wallet could (and
did, in the 2026-09-19 "vault" incident) lose a large fraction of its
tracked value in a single silent write. The write itself wasn't wrong --
save_balance() faithfully stored whatever it was given -- there was just no
signal that the given value was a huge change worth a human's attention.

Design constraint: ALERT, never block. A user legitimately moving funds out
produces the same signal as a bug; refusing the write would corrupt real
data. So every test here also asserts the write itself still succeeds with
the new value, anomaly or not.

Percentage-based (BALANCE_ANOMALY_PCT_THRESHOLD, default 0.5 / 50%), not
absolute, because save_balance() has no price context to make an absolute
threshold meaningful across chains.
"""

import os
import sqlite3
import sys
from datetime import datetime

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402

WALLET_ID = 1
USER_ID = 1


def _make_test_db(tmp_path, initial_amount=None, blockchain="cardano"):
    db_path = str(tmp_path / "test_anomaly.db")
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
    conn.execute(
        "INSERT INTO wallets (id, user_id, address, blockchain, label) VALUES (?, ?, ?, ?, ?)",
        (WALLET_ID, USER_ID, "addr_test", blockchain, "Test Wallet"),
    )
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
    if initial_amount is not None:
        conn.execute(
            "INSERT INTO balances (wallet_id, user_id, amount, unit, updated_at) VALUES (?, ?, ?, ?, ?)",
            (WALLET_ID, USER_ID, initial_amount, "ADA", datetime.now()),
        )
    conn.execute("""
        CREATE TABLE balance_anomalies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            blockchain TEXT,
            unit TEXT NOT NULL,
            old_value TEXT NOT NULL,
            new_value TEXT NOT NULL,
            pct_change REAL NOT NULL,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    return db_path


@pytest.mark.asyncio
async def test_large_drop_is_flagged_persisted_and_write_still_succeeds(tmp_path, monkeypatch):
    db_path = _make_test_db(tmp_path, initial_amount="36958.050955")
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    monkeypatch.setattr(database, "BALANCE_ANOMALY_PCT_THRESHOLD", 0.5)

    # The actual incident shape: a wallet drops to ~44% of its stored value.
    await database.save_balance(WALLET_ID, "16444.404966", "ADA", user_id=USER_ID)

    # The write must still have succeeded with the NEW value -- never blocked.
    current = await database.get_wallet_balance(WALLET_ID)
    assert current["amount"] == "16444.404966"

    # And it must be persisted to the DB, not just logged.
    anomalies = await database.get_recent_balance_anomalies(USER_ID)
    assert len(anomalies) == 1
    row = anomalies[0]
    assert row["wallet_id"] == WALLET_ID
    assert row["blockchain"] == "cardano"
    assert row["unit"] == "ADA"
    assert row["old_value"] == "36958.050955"
    assert row["new_value"] == "16444.404966"
    assert row["pct_change"] < -0.5  # a drop, expressed negative, past threshold


@pytest.mark.asyncio
async def test_normal_small_change_is_not_flagged(tmp_path, monkeypatch):
    db_path = _make_test_db(tmp_path, initial_amount="100.0")
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    monkeypatch.setattr(database, "BALANCE_ANOMALY_PCT_THRESHOLD", 0.5)

    # A 10% change -- ordinary organic activity, well under the threshold.
    await database.save_balance(WALLET_ID, "110.0", "ADA", user_id=USER_ID)

    current = await database.get_wallet_balance(WALLET_ID)
    assert current["amount"] == "110.0"

    anomalies = await database.get_recent_balance_anomalies(USER_ID)
    assert anomalies == []


@pytest.mark.asyncio
async def test_first_ever_write_is_not_flagged(tmp_path, monkeypatch):
    db_path = _make_test_db(tmp_path, initial_amount=None)  # no prior row at all
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    monkeypatch.setattr(database, "BALANCE_ANOMALY_PCT_THRESHOLD", 0.5)

    await database.save_balance(WALLET_ID, "50000.0", "ADA", user_id=USER_ID)

    current = await database.get_wallet_balance(WALLET_ID)
    assert current["amount"] == "50000.0"

    anomalies = await database.get_recent_balance_anomalies(USER_ID)
    assert anomalies == []


@pytest.mark.asyncio
async def test_zero_to_funded_is_not_flagged(tmp_path, monkeypatch):
    db_path = _make_test_db(tmp_path, initial_amount="0")
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    monkeypatch.setattr(database, "BALANCE_ANOMALY_PCT_THRESHOLD", 0.5)

    await database.save_balance(WALLET_ID, "1000.0", "ADA", user_id=USER_ID)

    current = await database.get_wallet_balance(WALLET_ID)
    assert current["amount"] == "1000.0"

    anomalies = await database.get_recent_balance_anomalies(USER_ID)
    assert anomalies == []


@pytest.mark.asyncio
async def test_anomaly_check_failure_never_breaks_the_write(tmp_path, monkeypatch):
    """The guard is best-effort -- a bug in the guard itself must not turn
    into a failed balance save."""
    db_path = _make_test_db(tmp_path, initial_amount="1000.0")
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    monkeypatch.setattr(database, "BALANCE_ANOMALY_PCT_THRESHOLD", 0.5)

    async def broken_check(*args, **kwargs):
        raise RuntimeError("guard exploded")

    monkeypatch.setattr(database, "_check_balance_anomaly", broken_check)

    # Must not raise.
    await database.save_balance(WALLET_ID, "1.0", "ADA", user_id=USER_ID)

    current = await database.get_wallet_balance(WALLET_ID)
    assert current["amount"] == "1.0"
