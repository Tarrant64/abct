"""
Regression tests for ABCT-BALANCE-ATOMIC-20260919.

Root cause: `clear_wallet_balances()` and (the old) `save_balance()`
(database.py:1419-1441, pre-fix) each opened and committed their OWN
separate aiosqlite connection. Every one of the ~53 call sites in
`_refresh_wallet_balance` (routers/wallets.py, one per chain, plus one in
routers/privacy.py for manual Monero entry) called them back-to-back:

    await clear_wallet_balances(wallet_id)   # commits: zero rows on disk
    await save_balance(wallet_id, amount, unit)  # commits: new row on disk

Between those two commits, a concurrent reader (get_wallet_balance /
get_wallet_balances_bulk) genuinely observed zero balance rows for that
wallet -- a portfolio tracker flashing $0. This was rare when refreshes were
only user-triggered; an hourly background sync (a later, separate piece of
work) would make it recurring, which is why this had to be fixed first.

Fix: `save_balance()` now does DELETE + INSERT on a single connection with a
single commit, so no other connection can ever observe the intermediate
state. The now-redundant standalone `clear_wallet_balances()` calls were
removed from all 53 call sites (52 in routers/wallets.py, 1 in
routers/privacy.py).

This file proves both halves with real concurrent asyncio tasks racing
against real aiosqlite connections on a real (temp) SQLite file --
deterministically, via asyncio.Event handshakes, not timing-dependent
sleeps:

1. test_legacy_two_call_sequence_exposes_zero_row_window -- reconstructs the
   exact pre-fix call shape (frozen copy of the old insert-only
   save_balance, called after clear_wallet_balances()) and proves a
   concurrent reader lands in the gap and sees zero rows. This is the "before"
   half: it demonstrates the vulnerability was real given that shape, not
   that any code today still has it.
2. test_current_save_balance_is_atomic_under_forced_interleaving -- races a
   concurrent reader against the REAL, current `database.save_balance()`,
   forcing the reader to run at the exact point between save_balance's
   internal DELETE and its INSERT+commit (via an aiosqlite.Connection.execute
   hook -- not a hopeful sleep(0)). Proves the reader never sees zero rows,
   and in fact still sees the pre-write value until the new one commits.

Together these are the "before" and "after" for the same defect: the first
test's assertion would be exactly what you'd see if you pointed it at any of
the 53 removed call sites; the second test's assertion is what the current
save_balance() guarantees and would fail again if someone re-introduced a
separate clear-then-insert-on-two-connections pattern.
"""

import asyncio
import os
import sqlite3
import sys
from datetime import datetime

import pytest
import aiosqlite

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402

WALLET_ID = 1
USER_ID = 1


def _make_balances_db(tmp_path, initial_amount="10.0", initial_unit="ADA"):
    """A minimal real SQLite file with just the `balances` table (schema
    matches database.py's CREATE TABLE), seeded with one existing row so
    a reader can distinguish "old value", "new value", and "zero rows"."""
    db_path = str(tmp_path / "test_balances.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            amount TEXT NOT NULL,
            unit TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
    """)
    conn.execute(
        "INSERT INTO balances (wallet_id, user_id, amount, unit, updated_at) VALUES (?, ?, ?, ?, ?)",
        (WALLET_ID, USER_ID, initial_amount, initial_unit, datetime.now()),
    )
    conn.commit()
    conn.close()
    return db_path


async def _legacy_save_balance_insert_only(db_path, wallet_id, amount, unit, user_id):
    """Frozen copy of save_balance() as it existed before
    ABCT-BALANCE-ATOMIC-20260919: a bare INSERT on its own connection/commit,
    with no delete. Kept here only to reconstruct the historical two-call
    sequence below -- the real save_balance() can no longer be split apart
    from outside since it's now atomic."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO balances (wallet_id, user_id, amount, unit, updated_at) VALUES (?, ?, ?, ?, ?)",
            (wallet_id, user_id, amount, unit, datetime.now()),
        )
        await db.commit()


@pytest.mark.asyncio
async def test_legacy_two_call_sequence_exposes_zero_row_window(tmp_path, monkeypatch):
    db_path = _make_balances_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)

    clear_committed = asyncio.Event()
    reader_finished = asyncio.Event()
    reader_result = {}

    async def legacy_refresh():
        # This is exactly what every one of the 53 removed call sites did.
        await database.clear_wallet_balances(WALLET_ID)  # own connection, own commit
        clear_committed.set()
        await reader_finished.wait()
        await _legacy_save_balance_insert_only(db_path, WALLET_ID, "25.0", "ADA", USER_ID)

    async def concurrent_reader():
        await clear_committed.wait()
        reader_result["balance"] = await database.get_wallet_balance(WALLET_ID)
        reader_finished.set()

    await asyncio.gather(legacy_refresh(), concurrent_reader())

    assert reader_result["balance"] is None, (
        "expected the legacy clear-then-insert-on-separate-connections "
        f"sequence to expose a zero-row window; reader instead saw {reader_result['balance']!r}"
    )


@pytest.mark.asyncio
async def test_current_save_balance_is_atomic_under_forced_interleaving(tmp_path, monkeypatch):
    db_path = _make_balances_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)

    delete_done = asyncio.Event()
    reader_finished = asyncio.Event()
    reader_result = {}

    original_execute = aiosqlite.Connection.execute

    async def spying_execute(self, sql, *args, **kwargs):
        result = await original_execute(self, sql, *args, **kwargs)
        if isinstance(sql, str) and sql.strip().startswith("DELETE FROM balances"):
            # We are now inside save_balance()'s single transaction, right
            # after its internal DELETE and before its INSERT+commit. Force
            # a concurrent reader (on a SEPARATE connection) to run here --
            # if save_balance() is truly atomic, SQLite must not expose this
            # uncommitted mid-transaction state to that other connection.
            delete_done.set()
            await reader_finished.wait()
        return result

    monkeypatch.setattr(aiosqlite.Connection, "execute", spying_execute)

    async def concurrent_reader():
        await delete_done.wait()
        reader_result["balance"] = await database.get_wallet_balance(WALLET_ID)
        reader_finished.set()

    await asyncio.gather(
        database.save_balance(WALLET_ID, "25.0", "ADA", user_id=USER_ID),
        concurrent_reader(),
    )

    assert reader_result["balance"] is not None, (
        "a concurrent reader observed a zero-row balance while the current "
        "save_balance() was mid-transaction -- atomicity regression"
    )
    assert reader_result["balance"]["amount"] == "10.0", (
        "expected the reader to see the pre-write balance (uncommitted "
        f"transaction should be invisible), got {reader_result['balance']!r}"
    )

    # After save_balance() completes, the new value must be the only row.
    final = await database.get_wallet_balance(WALLET_ID)
    assert final["amount"] == "25.0"
