"""
Unit tests for the batched wallet lookup helpers (DASHBOARD-1).

Verifies that get_wallet_balances_bulk / get_wallet_asset_counts_bulk return
exactly what per-wallet get_wallet_balance / len(get_wallet_assets) calls
return, on a seeded temp database. /api/mobile/wallets relies on this
equivalence for its response shape to stay byte-identical.

These tests use a temp SQLite DB and do NOT require a running server.
"""

import os
import sqlite3
import sys

import pytest

# Add backend to sys.path so imports work
BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402


@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    """Temp DB: 3 wallets — multi-balance, single-balance, empty — plus a
    hidden token for user 1 and an identical un-hidden token for user 2."""
    db_path = tmp_path / "portfolio.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
    CREATE TABLE wallets (id INTEGER PRIMARY KEY, user_id INTEGER, blockchain TEXT,
        address TEXT, label TEXT, created_at TEXT, updated_at TEXT);
    CREATE TABLE balances (id INTEGER PRIMARY KEY, wallet_id INTEGER, amount REAL, updated_at TEXT);
    CREATE TABLE native_assets (id INTEGER PRIMARY KEY, wallet_id INTEGER, user_id INTEGER,
        policy_id TEXT, asset_id TEXT, asset_name TEXT);
    CREATE TABLE hidden_tokens (id INTEGER PRIMARY KEY, user_id INTEGER, blockchain TEXT,
        token_address TEXT);
    """)
    conn.executemany("INSERT INTO wallets VALUES (?,?,?,?,?,?,?)", [
        (1, 1, 'cardano', 'addr1', 'A', '2026-01-01', None),
        (2, 1, 'bitcoin', 'bc1', 'B', '2026-01-02', None),
        (3, 1, 'ethereum', '0x3', 'C', '2026-01-03', None),
        (4, 2, 'cardano', 'addr4', 'D', '2026-01-04', None),
    ])
    conn.executemany("INSERT INTO balances VALUES (?,?,?,?)", [
        (1, 1, 100.0, '2026-06-01T00:00:00'),
        (2, 1, 200.0, '2026-06-15T00:00:00'),  # latest for wallet 1
        (3, 1, 50.0, '2026-05-01T00:00:00'),
        (4, 2, 0.75, '2026-06-20T00:00:00'),
        # wallet 3 has no balance rows
        (5, 4, 999.0, '2026-06-21T00:00:00'),
    ])
    conn.executemany("INSERT INTO native_assets VALUES (?,?,?,?,?,?)", [
        (1, 1, 1, 'policyA', 'assetA', 'TokenA'),
        (2, 1, 1, 'policyB', 'assetB', 'TokenB'),
        (3, 1, 1, 'policyHIDDEN', 'assetH', 'Spam'),   # hidden for user 1
        (4, 4, 2, 'policyHIDDEN', 'assetH', 'Spam'),   # user 2: not hidden
    ])
    conn.execute("INSERT INTO hidden_tokens VALUES (1, 1, 'cardano', 'policyHIDDEN')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    return db_path


async def test_bulk_balances_match_single_calls(seeded_db):
    wallet_ids = [1, 2, 3, 4]
    bulk = await database.get_wallet_balances_bulk(wallet_ids)
    for wid in wallet_ids:
        single = await database.get_wallet_balance(wid)
        assert bulk.get(wid) == single, f"wallet {wid} mismatch"
    # wallet 3 has no balances: absent from bulk, None from single
    assert 3 not in bulk


async def test_bulk_balances_pick_latest_row(seeded_db):
    bulk = await database.get_wallet_balances_bulk([1])
    assert bulk[1]['amount'] == 200.0
    assert bulk[1]['updated_at'] == '2026-06-15T00:00:00'


async def test_bulk_asset_counts_match_single_calls(seeded_db):
    wallet_ids = [1, 2, 3, 4]
    bulk = await database.get_wallet_asset_counts_bulk(wallet_ids)
    for wid in wallet_ids:
        assets = await database.get_wallet_assets(wid)
        assert bulk.get(wid, 0) == len(assets), f"wallet {wid} mismatch"
    # hidden_tokens exclusion is per-user: user 1's spam hidden, user 2's not
    assert bulk[1] == 2
    assert bulk[4] == 1


async def test_bulk_helpers_empty_input(seeded_db):
    assert await database.get_wallet_balances_bulk([]) == {}
    assert await database.get_wallet_asset_counts_bulk([]) == {}
