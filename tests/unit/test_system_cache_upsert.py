"""
Unit tests for ABCT-NFT-DIAG-2026-09-27 (system-wide cache rows piling up).

The cache table has UNIQUE(user_id, key), but SQLite treats NULLs as distinct,
so ``set_cache(key, ..., user_id=None)`` never hit its ON CONFLICT upsert and
inserted a fresh row on every write. ``get_cache`` then read whichever row
came first, which was the OLDEST. A production snapshot had 1057 system-wide
rows for 127 keys, and the NFT caches were read back as long-expired entries,
so every restart re-fetched from the providers.

Uses a throwaway SQLite file with the production cache schema.
"""

import os
import sqlite3
import sys
from datetime import datetime, timedelta

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402

SCHEMA = """
CREATE TABLE users (id INTEGER PRIMARY KEY);
CREATE TABLE cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE(user_id, key),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
INSERT INTO users (id) VALUES (1);
"""


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "cache_test.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    monkeypatch.setattr(database, "DATABASE_PATH", str(path))
    return path


def _rows(path, key, user_id=None):
    conn = sqlite3.connect(path)
    if user_id is None:
        rows = conn.execute("SELECT id, value FROM cache WHERE user_id IS NULL AND key = ?", (key,)).fetchall()
    else:
        rows = conn.execute("SELECT id, value FROM cache WHERE user_id = ? AND key = ?", (user_id, key)).fetchall()
    conn.close()
    return rows


async def test_system_wide_set_cache_updates_in_place(db_path):
    for i in range(5):
        await database.set_cache("eth_nft_all_data", {"n": i}, ttl_seconds=3600)
    assert len(_rows(db_path, "eth_nft_all_data")) == 1
    assert await database.get_cache("eth_nft_all_data") == {"n": 4}


async def test_user_scoped_upsert_unchanged(db_path):
    for i in range(3):
        await database.set_cache("nft_all_data", {"n": i}, ttl_seconds=3600, user_id=1)
    assert len(_rows(db_path, "nft_all_data", user_id=1)) == 1
    assert await database.get_cache("nft_all_data", user_id=1) == {"n": 2}
    # system-wide and user-scoped entries with the same key stay separate
    await database.set_cache("nft_all_data", {"sys": True}, ttl_seconds=3600)
    assert await database.get_cache("nft_all_data") == {"sys": True}
    assert await database.get_cache("nft_all_data", user_id=1) == {"n": 2}


async def test_legacy_duplicates_read_newest_and_heal_on_write(db_path):
    # Simulate the pre-fix state: an old EXPIRED row first, a newer valid row after it
    conn = sqlite3.connect(db_path)
    old = (datetime.now() - timedelta(days=7)).isoformat()
    new = (datetime.now() + timedelta(days=7)).isoformat()
    conn.execute("INSERT INTO cache (user_id, key, value, expires_at) VALUES (NULL, 'sol_nft_all_data', '{\"v\": \"old\"}', ?)", (old,))
    conn.execute("INSERT INTO cache (user_id, key, value, expires_at) VALUES (NULL, 'sol_nft_all_data', '{\"v\": \"new\"}', ?)", (new,))
    conn.commit()
    conn.close()

    # Before the fix get_cache returned the oldest (expired) row -> None
    assert await database.get_cache("sol_nft_all_data") == {"v": "new"}
    data, _ = await database.get_stale_cache("sol_nft_all_data")
    assert data == {"v": "new"}

    await database.set_cache("sol_nft_all_data", {"v": "newest"}, ttl_seconds=3600)
    values = {v for _, v in _rows(db_path, "sol_nft_all_data")}
    assert values == {'{"v": "newest"}'}  # every legacy duplicate now agrees
    assert await database.get_cache("sol_nft_all_data") == {"v": "newest"}
