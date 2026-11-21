"""
ABCT-DECIMALS-20261121: native_assets.decimals stuck at 0 for Cardano tokens whose registry / Blockfrost /
Koios metadata carries real decimals.

Pins the safe rule: a stored 0/NULL yields to VERIFIED metadata decimals (exact policy+name, source in
registry/blockfrost/koios), a non-zero stored value is never overridden, nothing is ever taken from a
ticker-matched ("market-cache") guess, non-Cardano rows are untouched, and the backfill is idempotent.
"""
import json
import os
import sqlite3
import sys

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402
import services.cardano_token_meta as ctm  # noqa: E402

POL = "ab" * 28
A_REG = POL + "44524950"        # registry, 6
A_STORED = POL + "01"           # stored 3, meta says 6 -> keep 3
A_MARKET = POL + "02"           # decimals only claimed by market-cache -> ignore
A_NONE = POL + "03"             # no meta row
A_KOIOS = POL + "04"            # koios, 2
A_CAP = POL + "05"              # absurd decimals -> ignore
ETH_ID = "0x" + "11" * 20       # non-Cardano id


def _db(tmp_path):
    path = tmp_path / "d.db"
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE wallets (id INTEGER PRIMARY KEY, user_id INTEGER, address TEXT, blockchain TEXT, label TEXT);
        CREATE TABLE native_assets (id INTEGER PRIMARY KEY AUTOINCREMENT, wallet_id INTEGER, user_id INTEGER,
            asset_id TEXT, policy_id TEXT, asset_name TEXT, quantity TEXT, decimals INTEGER DEFAULT 0,
            ignored INTEGER DEFAULT 0, updated_at TIMESTAMP);
        CREATE TABLE token_metadata (asset_id TEXT PRIMARY KEY, policy_id TEXT, asset_name TEXT, ticker TEXT,
            name TEXT, decimals INTEGER DEFAULT 0, logo_url TEXT, track_for_pricing INTEGER DEFAULT 0, updated_at TIMESTAMP);
        INSERT INTO wallets VALUES (1, 1, 'addr1', 'cardano', NULL);
        INSERT INTO wallets VALUES (2, 1, '0xabc', 'ethereum', NULL);
    """)
    rows = [(A_REG, 0), (A_STORED, 3), (A_MARKET, 0), (A_NONE, 0), (A_KOIOS, None), (A_CAP, 0), (ETH_ID, 0)]
    for aid, dec in rows:
        wid = 2 if aid == ETH_ID else 1
        c.execute("INSERT INTO native_assets (wallet_id,user_id,asset_id,policy_id,quantity,decimals) VALUES (?,1,?,?,?,?)",
                  (wid, aid, POL, "1000000", dec))
    c.execute("INSERT INTO token_metadata (asset_id, decimals) VALUES (?, 0)", (A_REG,))
    c.commit()
    c.close()
    return path


def _seed_meta(path):
    c = sqlite3.connect(path)
    c.execute("""CREATE TABLE IF NOT EXISTS cardano_token_meta (asset_id TEXT PRIMARY KEY, policy_id TEXT NOT NULL,
        name_hex TEXT NOT NULL, name TEXT, ticker TEXT, decimals INTEGER, coingecko_id TEXT, logo_ref TEXT,
        has_logo INTEGER DEFAULT 0, sources TEXT, status TEXT, checked_at REAL, expires_at REAL)""")
    meta = [
        (A_REG, 6, ["registry"]),
        (A_STORED, 6, ["registry"]),
        (A_MARKET, 8, ["market-cache"]),
        (A_KOIOS, 2, ["koios"]),
        (A_CAP, 99, ["registry"]),
        (ETH_ID, 6, ["registry"]),
    ]
    for aid, dec, src in meta:
        c.execute("INSERT INTO cardano_token_meta (asset_id,policy_id,name_hex,decimals,sources,status,expires_at) VALUES (?,?,?,?,?,?,?)",
                  (aid, POL, aid[56:], dec, json.dumps(src), "found", 0))  # expired rows still count
    c.commit()
    c.close()


def _dec(path):
    c = sqlite3.connect(path)
    try:
        return dict(c.execute("SELECT asset_id, decimals FROM native_assets").fetchall())
    finally:
        c.close()


@pytest.fixture
def env(tmp_path, monkeypatch):
    path = _db(tmp_path)
    monkeypatch.setattr(ctm, "DATABASE_PATH", str(path))
    monkeypatch.setattr(database, "DATABASE_PATH", str(path))
    ctm._reset_for_tests()
    _seed_meta(path)
    return path


def test_pure_rules():
    ok = {"decimals": 6, "sources": json.dumps(["registry"])}
    assert ctm.authoritative_decimals(ok) == 6
    assert ctm.authoritative_decimals({"decimals": 6, "sources": ["blockfrost", "market-cache"]}) == 6
    assert ctm.authoritative_decimals({"decimals": 6, "sources": ["market-cache"]}) is None
    assert ctm.authoritative_decimals({"decimals": 0, "sources": ["registry"]}) is None
    assert ctm.authoritative_decimals({"decimals": None, "sources": ["registry"]}) is None
    assert ctm.authoritative_decimals({"decimals": 31, "sources": ["registry"]}) is None
    assert ctm.authoritative_decimals({"decimals": True, "sources": ["registry"]}) is None
    assert ctm.authoritative_decimals({"decimals": 6, "sources": "not json"}) is None
    assert ctm.authoritative_decimals(None) is None
    assert ctm.effective_decimals(0, ok) == 6
    assert ctm.effective_decimals(None, ok) == 6
    assert ctm.effective_decimals(3, ok) == 3          # never override a non-zero stored value
    assert ctm.effective_decimals(0, None) == 0


async def test_backfill_fixes_only_verified_zero_rows(env):
    changed = await ctm.sync_native_asset_decimals()
    assert changed == 2                                  # A_REG + A_KOIOS; the Ethereum-wallet row is untouched
    d = _dec(env)
    assert d[A_REG] == 6
    assert d[A_KOIOS] == 2
    assert d[A_STORED] == 3                              # non-zero kept
    assert d[A_MARKET] == 0                              # market-cache is a ticker guess: ignored
    assert d[A_NONE] == 0                                # no metadata
    assert d[A_CAP] == 0                                 # implausible decimals ignored
    assert d[ETH_ID] == 0                                # non-Cardano wallet row untouched
    c = sqlite3.connect(env)
    assert c.execute("SELECT decimals FROM token_metadata WHERE asset_id=?", (A_REG,)).fetchone()[0] == 6
    c.close()


async def test_backfill_is_idempotent(env):
    assert await ctm.sync_native_asset_decimals() == 2
    before = _dec(env)
    assert await ctm.sync_native_asset_decimals() == 0
    assert _dec(env) == before


async def test_backfill_survives_missing_tables(tmp_path, monkeypatch):
    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()
    monkeypatch.setattr(ctm, "DATABASE_PATH", str(path))
    ctm._reset_for_tests()
    assert await ctm.sync_native_asset_decimals() == 0


async def test_single_asset_sync_leaves_others(env):
    assert await ctm.sync_native_asset_decimals(asset_id=A_REG) == 1
    assert _dec(env)[A_KOIOS] in (0, None)


async def test_fill_asset_decimals_for_refresh_payload(env):
    assets = [{"asset_id": A_REG, "policy_id": POL, "decimals": 0},
              {"asset_id": A_STORED, "policy_id": POL, "decimals": 3},
              {"asset_id": A_MARKET, "policy_id": POL, "decimals": None},
              {"asset_id": ETH_ID, "decimals": 0},
              {"asset_id": "", "decimals": 0}]
    assert await ctm.fill_asset_decimals(assets) == 1
    assert [a["decimals"] for a in assets] == [6, 3, None, 0, 0]


async def test_save_native_assets_applies_metadata_decimals(env):
    """A wallet refresh (delete + insert with decimals 0) must not re-introduce the stored 0."""
    await database.save_native_assets(1, [
        {"asset_id": A_REG, "policy_id": POL, "asset_name": "DRIP", "quantity": "24029539420", "decimals": 0},
        {"asset_id": A_MARKET, "policy_id": POL, "asset_name": "X", "quantity": "5", "decimals": 0},
    ])
    d = _dec(env)
    assert d[A_REG] == 6 and d[A_MARKET] == 0


async def test_resolve_save_triggers_sync(env, monkeypatch):
    """Resolving a token through the chain writes decimals through to native_assets immediately."""
    c = sqlite3.connect(env)
    c.execute("DELETE FROM cardano_token_meta")
    c.commit()
    c.close()
    ctm._reset_for_tests()

    async def reg(p, n):
        return {"ticker": "DRIP", "name": "Drip", "decimals": 6}

    async def none(*a, **k):
        return None
    monkeypatch.setattr(ctm, "fetch_registry", reg)
    monkeypatch.setattr(ctm, "fetch_blockfrost", none)
    monkeypatch.setattr(ctm, "fetch_koios", none)
    monkeypatch.setattr(ctm, "fetch_cached_market", none)
    monkeypatch.setattr(ctm, "fetch_image_bytes", none)
    await ctm.resolve(POL, "44524950", force=True)
    assert _dec(env)[A_REG] == 6


def test_quantity_math_before_after():
    raw = 24029539420
    assert raw / (10 ** 0) == 24029539420            # before: raw units shown as whole tokens
    assert raw / (10 ** 6) == pytest.approx(24029.53942)   # after
