"""
Regression tests for ABCT-CARDANO-ACCOUNT-LEVEL-20260919.

Root cause of the 2026-09-19 "vault" incident: ABCT summed individually
registered Cardano payment addresses instead of querying the stake account
they belong to. A hardware wallet reports the whole account; ABCT only ever
saw as much as the user had manually registered -- the vault's account had
11 real addresses, ABCT tracked 9, and the missing ~20,514 ADA sat in the 2
it never knew about. cardano_service.get_stake_account_info() already
existed and was already being called (get_stake_address_totals()) -- and
then discarded in favor of looping addresses anyway. That's the bug in one
sentence.

Fix: _refresh_wallet_balance's Cardano branch now resolves each wallet's
stake key (once, persisted forever -- a payment address's stake credential
never changes), and for wallets that share a stake key, exactly ONE
"canonical" member fetches the account-level balance (Koios primary,
Blockfrost fallback) and every other member's balance is written as 0 in
the same operation -- collapsing the group's contribution to SUM(balances)
to exactly once, not N times. Canonical selection prefers a user-set label
over an auto-generated one (e.g. stake rediscovery's "Discovered (...)"),
tiebreaking on the lowest wallet id.

Mocks cardano_service and taptools_wallet_service -- no live provider
calls. Exercises the real database.py functions (save_wallet,
get_stake_group_wallets, save_balance, set_wallet_stake_address) against a
real temporary SQLite file.
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
import routers.wallets as wallets_router  # noqa: E402
import services.cardano as cardano_module  # noqa: E402

USER_ID = 1
STAKE_ADDRESS = "stake1uxvaultkey000000000000000000000000000000000000000000"


def _make_test_db(tmp_path):
    db_path = str(tmp_path / "test_account_level.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            address TEXT NOT NULL,
            blockchain TEXT NOT NULL,
            label TEXT,
            label_is_auto INTEGER DEFAULT 0,
            stake_address TEXT,
            ada_handle TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, address, blockchain)
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
        CREATE TABLE native_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            asset_id TEXT, policy_id TEXT, asset_name TEXT,
            quantity TEXT, decimals INTEGER, ignored INTEGER DEFAULT 0,
            updated_at TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    return db_path


def _insert_wallet(db_path, address, label=None, label_is_auto=0, stake_address=None, user_id=USER_ID):
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "INSERT INTO wallets (user_id, address, blockchain, label, label_is_auto, stake_address) "
        "VALUES (?, ?, 'cardano', ?, ?, ?)",
        (user_id, address, label, label_is_auto, stake_address),
    )
    conn.commit()
    wallet_id = cur.lastrowid
    conn.close()
    return wallet_id


@pytest.mark.asyncio
async def test_vault_nine_wallets_sum_to_account_total_not_nine_times(tmp_path, monkeypatch):
    """The test team-lead cares most about: 9 wallets, 1 stake key, the
    account total must appear exactly once in SUM(balances), not 9x."""
    db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)

    wallet_ids = []
    for i in range(9):
        wid = _insert_wallet(db_path, f"addr1_vault_{i}", label="vault" if i == 3 else None,
                              stake_address=STAKE_ADDRESS)
        wallet_ids.append(wid)
    # Wallet at index 3 has the user's real label "vault" -- give it a
    # HIGHER id than some others to prove label preference beats id order.
    canonical_expected = wallet_ids[3]

    async def fake_get_wallet_portfolio(address):
        return {
            "utxo_ada": 36958.050955,
            "rewards_available_ada": 1393.039880,
            "total_balance_ada": 38351.090835,
        }

    monkeypatch.setattr(wallets_router.taptools_wallet_service, "get_wallet_portfolio", fake_get_wallet_portfolio)

    # Refresh every wallet in the group (as a bulk refresh or bgsync cycle would).
    for i, wid in enumerate(wallet_ids):
        wallet = await database.get_wallet_by_address(f"addr1_vault_{i}", "cardano", user_id=USER_ID)
        await wallets_router._refresh_wallet_balance(wallet)

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT wallet_id, amount FROM balances").fetchall()
    conn.close()
    total = sum(float(amount) for _, amount in rows)

    assert total == pytest.approx(36958.050955), f"expected the account total once, got sum={total}"

    canonical_row = [r for r in rows if r[0] == canonical_expected]
    assert canonical_row and float(canonical_row[0][1]) == pytest.approx(36958.050955)

    # Every other wallet in the group must be exactly zero.
    other_rows = [r for r in rows if r[0] != canonical_expected]
    assert all(float(amount) == 0.0 for _, amount in other_rows)


@pytest.mark.asyncio
async def test_canonical_selection_prefers_user_label_over_auto(tmp_path, monkeypatch):
    db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)

    # Auto-labeled wallet added FIRST (lower id) by stake rediscovery.
    auto_id = _insert_wallet(db_path, "addr1_auto", label="Discovered (stake1uxv...)",
                              label_is_auto=1, stake_address=STAKE_ADDRESS)
    # User's own labeled wallet added SECOND (higher id).
    user_id_wallet = _insert_wallet(db_path, "addr1_user", label="vault",
                                     label_is_auto=0, stake_address=STAKE_ADDRESS)

    group = await database.get_stake_group_wallets(USER_ID, STAKE_ADDRESS)
    assert group[0]["id"] == user_id_wallet, "user-set label must win over auto-generated even with a higher id"
    assert auto_id != group[0]["id"]


@pytest.mark.asyncio
async def test_enterprise_address_without_stake_key_uses_per_address_path_unchanged(tmp_path, monkeypatch):
    db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    wallet_id = _insert_wallet(db_path, "addr1_enterprise", stake_address=None)

    async def fake_get_stake_address(address):
        return None  # enterprise address: no stake component

    async def fake_get_address_info(address):
        return {"balance_ada": "42.0", "native_assets": [], "source": "blockfrost"}

    portfolio_called = []

    async def fake_get_wallet_portfolio(address):
        portfolio_called.append(address)
        return None

    monkeypatch.setattr(cardano_module.cardano_service, "get_stake_address", fake_get_stake_address)
    monkeypatch.setattr(cardano_module.cardano_service, "get_address_info", fake_get_address_info)
    monkeypatch.setattr(wallets_router.taptools_wallet_service, "get_wallet_portfolio", fake_get_wallet_portfolio)

    wallet = await database.get_wallet_by_address("addr1_enterprise", "cardano", user_id=USER_ID)
    result = await wallets_router._refresh_wallet_balance(wallet)

    assert result["success"] is True
    assert result["balance"] == "42.0"
    assert result["source"] == "blockfrost"
    assert portfolio_called == [], "an enterprise address must never hit the account-level path"


@pytest.mark.asyncio
async def test_blockfrost_fallback_arithmetic_matches_koios_fixture():
    """Fixture-verify the controlled_amount - withdrawable_amount identity
    against the real numbers gathered for the vault (no live call) before
    the Blockfrost fallback path is trusted."""
    import services.cardano as cm

    svc = cm.CardanoService.__new__(cm.CardanoService)

    async def fake_get_stake_account_info(stake_address):
        return {
            "controlled_ada": 38351.090835,  # == Koios total_balance
            "withdrawable_ada": 1393.039880,  # == Koios rewards_available
        }

    svc.get_stake_account_info = fake_get_stake_account_info
    utxo = await cm.CardanoService.get_account_utxo_ada(svc, STAKE_ADDRESS)
    assert utxo == pytest.approx(36958.050955)  # == Koios utxo, exactly


# --- Commit 3: account-level native assets --------------------------------
#
# Same missing-address bug, token half: STRIKE/INDY/LQ (and everything
# else) sitting in an unregistered address were invisible the same way ADA
# was. Fix: source token quantity/existence from Koios's account_assets
# (already fetched via get_wallet_portfolio for the ADA balance -- one call
# now does both), attributed to the canonical wallet only. Same
# write-time-collapse dedup as ADA: a token existing 9x in a stake group
# must appear in native_assets exactly once, not 9 times.


def _insert_native_asset(db_path, wallet_id, asset_id, quantity="1", user_id=USER_ID):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO native_assets (wallet_id, user_id, asset_id, policy_id, asset_name, quantity, decimals) "
        "VALUES (?, ?, ?, '', '', ?, 0)",
        (wallet_id, user_id, asset_id, quantity),
    )
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_native_assets_appear_once_per_stake_group_not_nine_times(tmp_path, monkeypatch):
    """The token-side twin of the ADA dedup test: 9 wallets, 1 stake key,
    a Koios account_assets list with 2 tokens -- each token must end up in
    native_assets exactly once (on the canonical wallet), never 9 times."""
    db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)

    wallet_ids = []
    for i in range(9):
        wid = _insert_wallet(db_path, f"addr1_vault_{i}", label="vault" if i == 3 else None,
                              stake_address=STAKE_ADDRESS)
        wallet_ids.append(wid)
    canonical_id = wallet_ids[3]

    # Pre-existing per-address rows on a couple of NON-canonical wallets --
    # simulating what the old per-address fetch left behind. These must be
    # cleared, not left to double-count alongside the canonical row.
    _insert_native_asset(db_path, wallet_ids[0], "policySTRIKE_stale", quantity="999")

    async def fake_get_wallet_portfolio(address):
        return {
            "utxo_ada": 36958.050955,
            "rewards_available_ada": 1393.039880,
            "positions": [
                {"unit": "policySTRIKE", "policy_id": "policy", "asset_name": "STRIKE",
                 "raw_quantity": 500, "decimals": 0},
                {"unit": "policyINDY", "policy_id": "policy2", "asset_name": "INDY",
                 "raw_quantity": 250, "decimals": 0},
            ],
        }

    monkeypatch.setattr(wallets_router.taptools_wallet_service, "get_wallet_portfolio", fake_get_wallet_portfolio)

    for i, wid in enumerate(wallet_ids):
        wallet = await database.get_wallet_by_address(f"addr1_vault_{i}", "cardano", user_id=USER_ID)
        await wallets_router._refresh_wallet_balance(wallet)

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT wallet_id, asset_id, quantity FROM native_assets").fetchall()
    conn.close()

    strike_rows = [r for r in rows if r[1] == "policySTRIKE"]
    indy_rows = [r for r in rows if r[1] == "policyINDY"]
    stale_rows = [r for r in rows if r[1] == "policySTRIKE_stale"]

    assert len(strike_rows) == 1 and strike_rows[0][0] == canonical_id and strike_rows[0][2] == "500"
    assert len(indy_rows) == 1 and indy_rows[0][0] == canonical_id and indy_rows[0][2] == "250"
    assert stale_rows == [], "a non-canonical member's stale per-address assets must be cleared, not left to double-count"


@pytest.mark.asyncio
async def test_ada_handle_detection_restored_for_grouped_wallet(tmp_path, monkeypatch):
    """ADA Handle detection reads per-address native_assets and went inert
    for grouped wallets once the ADA-only commit stopped calling the
    per-address fetch for them. Restored via account-level assets here --
    a strict superset of what the old per-address fetch could ever find."""
    db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    wallet_id = _insert_wallet(db_path, "addr1_handle_wallet", label="vault", stake_address=STAKE_ADDRESS)

    handle_asset_name = "chriscata"
    handle_policy_id = "f0ff48bbb7bbe9d59a40f1ce90e9e9d0ff5002ec48f232b49ca0fb9a"  # ADA_HANDLE_POLICY_ID

    async def fake_get_wallet_portfolio(address):
        return {
            "utxo_ada": 100.0,
            "rewards_available_ada": 0.0,
            "positions": [
                {"unit": f"{handle_policy_id}{handle_asset_name}", "policy_id": handle_policy_id,
                 "asset_name": handle_asset_name, "raw_quantity": 1, "decimals": 0},
            ],
        }

    monkeypatch.setattr(wallets_router.taptools_wallet_service, "get_wallet_portfolio", fake_get_wallet_portfolio)

    wallet = await database.get_wallet_by_address("addr1_handle_wallet", "cardano", user_id=USER_ID)
    result = await wallets_router._refresh_wallet_balance(wallet)

    assert result["ada_handle"] == "$chriscata"

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT ada_handle FROM wallets WHERE id = ?", (wallet_id,)).fetchone()
    conn.close()
    assert row[0] == "$chriscata"


@pytest.mark.asyncio
async def test_enterprise_address_native_assets_path_still_unaffected(tmp_path, monkeypatch):
    """Enterprise addresses (no stake key) must keep using the original
    per-address native_assets fetch, completely untouched by commit 3."""
    db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    _insert_wallet(db_path, "addr1_enterprise2", stake_address=None)

    async def fake_get_stake_address(address):
        return None

    async def fake_get_address_info(address):
        return {
            "balance_ada": "10.0",
            "native_assets": [{"asset_id": "policyX", "policy_id": "p", "asset_name": "X",
                                "quantity": "3", "decimals": 0}],
            "source": "blockfrost",
        }

    portfolio_called = []

    async def fake_get_wallet_portfolio(address):
        portfolio_called.append(address)
        return None

    monkeypatch.setattr(cardano_module.cardano_service, "get_stake_address", fake_get_stake_address)
    monkeypatch.setattr(cardano_module.cardano_service, "get_address_info", fake_get_address_info)
    monkeypatch.setattr(wallets_router.taptools_wallet_service, "get_wallet_portfolio", fake_get_wallet_portfolio)

    wallet = await database.get_wallet_by_address("addr1_enterprise2", "cardano", user_id=USER_ID)
    result = await wallets_router._refresh_wallet_balance(wallet)

    assert result["success"] is True
    assert result["native_assets_count"] == 1
    assert portfolio_called == []
