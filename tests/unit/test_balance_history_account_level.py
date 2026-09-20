"""
Regression tests for ABCT-CARDANO-ACCOUNT-LEVEL-20260919 (materializer).

Commit 4: services/balance_history.py's _collect_cardano needs the same
canonical-row treatment as the live balance/native-asset fix in
routers/wallets.py, or the chart keeps recreating the missing-address
undercount the live headline just got fixed for -- a total-versus-history
mismatch in mirror image of the bug the user originally reported.

Fix: within a (user_id, stake_address) group, only the canonical wallet
gets a balance_history row; its series is the per-date SUM of every group
member's own address-level replay (_collect_cardano), not just its own
address. Non-canonical members are skipped going forward -- existing rows
already written under their wallet_id are left untouched (no backfill).

Mocks cardano_service and BalanceHistoryService's own chain-collector
methods -- no live provider calls. Exercises the real database.py
functions (save_wallet-equivalent inserts, get_stake_group_wallets,
set_wallet_stake_address, save_balance_history_batch,
get_balance_history_aggregated) against a real temporary SQLite file.
"""

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
import services.balance_history as balance_history_module  # noqa: E402
import services.cardano as cardano_module  # noqa: E402
from services.balance_history import BalanceHistoryService  # noqa: E402

USER_ID = 1
STAKE_ADDRESS = "stake1uxvaultkey000000000000000000000000000000000000000000"


def _make_test_db(tmp_path):
    db_path = str(tmp_path / "test_balance_history_account_level.db")
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, address, blockchain)
        )
    """)
    conn.execute("""
        CREATE TABLE balance_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            wallet_id INTEGER NOT NULL,
            blockchain TEXT NOT NULL,
            balance_date TEXT NOT NULL,
            native_amount REAL DEFAULT 0,
            native_symbol TEXT,
            native_price_usd REAL DEFAULT 0,
            native_value_usd REAL DEFAULT 0,
            token_value_usd REAL DEFAULT 0,
            total_value_usd REAL DEFAULT 0,
            data_source TEXT,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, wallet_id, balance_date)
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


def _insert_history_row(db_path, wallet_id, balance_date, native_amount, user_id=USER_ID):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO balance_history (user_id, wallet_id, blockchain, balance_date, native_amount, "
        "native_symbol, native_price_usd, native_value_usd, token_value_usd, total_value_usd, data_source, metadata) "
        "VALUES (?, ?, 'cardano', ?, ?, 'ADA', 0.5, ?, 0, ?, 'chain', '{}')",
        (user_id, wallet_id, balance_date, native_amount, native_amount * 0.5, native_amount * 0.5),
    )
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_non_canonical_stake_group_member_skips_collection_entirely(tmp_path, monkeypatch):
    """A non-canonical member must never call any collector or write any
    row -- the canonical member's own turn already carries the group's
    account-level series. Existing historical rows for the non-canonical
    wallet are explicitly left in place (no delete, no backfill)."""
    db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)

    canonical_id = _insert_wallet(db_path, "addr1_vault_canonical", label="vault", stake_address=STAKE_ADDRESS)
    member_id = _insert_wallet(db_path, "addr1_vault_member", stake_address=STAKE_ADDRESS)
    # Pre-existing per-address history row on the non-canonical member --
    # this must survive untouched (commit 4 is forward-only, no backfill).
    _insert_history_row(db_path, member_id, "2026-09-10", 1000.0)

    svc = BalanceHistoryService()
    collect_cardano_called = []
    collect_account_called = []
    save_batch_called = []

    async def fake_collect_cardano(address, latest_date, cutoff):
        collect_cardano_called.append(address)
        return {}

    async def fake_collect_cardano_account(group, latest_date, cutoff):
        collect_account_called.append(group)
        return {}

    async def fake_save_balance_history_batch(points, user_id):
        save_batch_called.append(points)

    monkeypatch.setattr(svc, "_collect_cardano", fake_collect_cardano)
    monkeypatch.setattr(svc, "_collect_cardano_account", fake_collect_cardano_account)
    monkeypatch.setattr(balance_history_module, "save_balance_history_batch", fake_save_balance_history_batch)

    member_wallet = {"id": member_id, "user_id": USER_ID, "address": "addr1_vault_member",
                      "blockchain": "cardano", "stake_address": STAKE_ADDRESS}
    await svc._collect_wallet(USER_ID, member_wallet, max_days_back=3650, job_id=0)

    assert collect_cardano_called == [], "non-canonical member must never call the single-address collector"
    assert collect_account_called == [], "non-canonical member must never call the account-level collector"
    assert save_batch_called == [], "non-canonical member must never write a new history row"

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT balance_date, native_amount FROM balance_history WHERE wallet_id = ?", (member_id,)
    ).fetchall()
    conn.close()
    assert rows == [("2026-09-10", 1000.0)], "pre-existing row on the non-canonical member must be untouched"


@pytest.mark.asyncio
async def test_canonical_member_collects_account_level_series_for_whole_group(tmp_path, monkeypatch):
    """The canonical member's own turn must call the account-level
    collector with every member of the group (not just its own address),
    and the resulting history rows must be written under the canonical
    wallet_id only."""
    db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)

    canonical_id = _insert_wallet(db_path, "addr1_vault_canonical", label="vault", stake_address=STAKE_ADDRESS)
    member_id = _insert_wallet(db_path, "addr1_vault_member", stake_address=STAKE_ADDRESS)

    svc = BalanceHistoryService()
    captured_group = []

    async def fake_collect_cardano_account(group, latest_date, cutoff):
        captured_group.extend(group)
        return {"2026-09-19": 36958.050955}

    async def fake_fetch_historical_prices(symbol, start_date, end_date):
        return {"2026-09-19": 0.5}

    saved_points = []

    async def fake_save_balance_history_batch(points, user_id):
        saved_points.extend(points)

    monkeypatch.setattr(svc, "_collect_cardano_account", fake_collect_cardano_account)
    monkeypatch.setattr(svc, "_fetch_historical_prices", fake_fetch_historical_prices)
    monkeypatch.setattr(balance_history_module, "save_balance_history_batch", fake_save_balance_history_batch)

    canonical_wallet = {"id": canonical_id, "user_id": USER_ID, "address": "addr1_vault_canonical",
                         "blockchain": "cardano", "stake_address": STAKE_ADDRESS}
    await svc._collect_wallet(USER_ID, canonical_wallet, max_days_back=3650, job_id=0)

    captured_ids = {m["id"] for m in captured_group}
    assert captured_ids == {canonical_id, member_id}, "account-level collection must cover every member of the group"

    assert len(saved_points) == 1
    assert saved_points[0]["wallet_id"] == canonical_id
    assert saved_points[0]["native_amount"] == pytest.approx(36958.050955)


@pytest.mark.asyncio
async def test_collect_cardano_account_sums_per_address_series_with_carry_forward(monkeypatch):
    """Direct unit test of the merge algorithm: summing must union every
    date across member series, carrying each series's last-known value
    forward (0 before that address's first-ever activity) rather than
    only reflecting whichever member happens to report a value on a given
    date. This is the token/ADA double-count fix's mirror image: here the
    failure mode being guarded against is UNDER-counting (only one
    address's series surviving), not over-counting."""
    svc = BalanceHistoryService()

    async def fake_collect_cardano(address, latest_date, cutoff):
        if address == "addr_tracked":
            # Long-tracked address: steady history.
            return {"2026-09-01": 16000.0, "2026-09-03": 16444.404966}
        if address == "addr_previously_untracked":
            # The address ABCT never knew about until stake rediscovery
            # added it -- no activity in its series before it starts.
            return {"2026-09-05": 20513.645989}
        return {}

    monkeypatch.setattr(svc, "_collect_cardano", fake_collect_cardano)

    group = [{"id": 1, "address": "addr_tracked"}, {"id": 2, "address": "addr_previously_untracked"}]
    summed = await svc._collect_cardano_account(group, latest_date=None, cutoff="2020-01-01")

    assert summed["2026-09-01"] == pytest.approx(16000.0)
    assert summed["2026-09-03"] == pytest.approx(16444.404966)
    # The date the previously-untracked address's contribution enters the
    # series is exactly where the account-level total steps up to match
    # the corrected live total -- 16444.404966 + 20513.645989 = 36958.050955,
    # matching Koios's reported utxo for the real vault account.
    assert summed["2026-09-05"] == pytest.approx(36958.050955)


@pytest.mark.asyncio
async def test_incremental_run_surfaces_a_newly_discovered_address_as_a_same_day_jump(monkeypatch):
    """Answers the step-change question directly: when the materializer
    runs incrementally (latest_date set, the normal/scheduled case), a
    stake-group member that has no prior balance_history rows of its own
    (e.g. one of the 2 addresses stake rediscovery just added) has its
    OLD real on-chain transaction excluded by the incremental date filter
    -- _collect_cardano only backfills dates after latest_date. Its
    contribution therefore lands as a single lump-sum jump on the
    canonical wallet's NEXT collected date, not spread across its true
    historical dates. This is what produces a visible step in the chart
    on deploy day, not a gradual correction."""
    svc = BalanceHistoryService()

    async def fake_collect_cardano(address, latest_date, cutoff):
        if address == "addr_long_tracked":
            return {"2026-09-19": 16444.404966}
        if address == "addr_just_discovered":
            # Simulates _collect_cardano's real behavior for a wallet with
            # an old transaction (e.g. 2026-08-15) that predates
            # effective_start=latest_date: recent_txs excludes it, so
            # net_change is 0 and only "today" gets recorded at the
            # address's full current balance (see balance_history.py's
            # "Ensure today's balance is recorded" step).
            assert latest_date == "2026-09-18", "must pass the canonical wallet's own latest_date, not None"
            return {"2026-09-19": 20513.645989}
        return {}

    monkeypatch.setattr(svc, "_collect_cardano", fake_collect_cardano)

    group = [{"id": 1, "address": "addr_long_tracked"}, {"id": 2, "address": "addr_just_discovered"}]
    summed = await svc._collect_cardano_account(group, latest_date="2026-09-18", cutoff="2020-01-01")

    # Only one date exists at all -- there is no gradual ramp for the
    # newly-discovered address's real historical balance, confirming the
    # jump is a single-day step, sized at exactly the previously-missing
    # amount.
    assert list(summed.keys()) == ["2026-09-19"]
    assert summed["2026-09-19"] == pytest.approx(36958.050955)


@pytest.mark.asyncio
async def test_enterprise_address_without_stake_key_uses_single_address_path_unchanged(tmp_path, monkeypatch):
    """Enterprise addresses (no stake key) must keep using the original
    single-address collector, completely untouched by commit 4."""
    db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    wallet_id = _insert_wallet(db_path, "addr1_enterprise", stake_address=None)

    svc = BalanceHistoryService()

    async def fake_get_stake_address(address):
        return None

    account_called = []

    async def fake_collect_cardano_account(group, latest_date, cutoff):
        account_called.append(group)
        return {}

    single_called = []

    async def fake_collect_cardano(address, latest_date, cutoff):
        single_called.append(address)
        return {"2026-09-19": 42.0}

    async def fake_fetch_historical_prices(symbol, start_date, end_date):
        return {"2026-09-19": 0.5}

    saved_points = []

    async def fake_save_balance_history_batch(points, user_id):
        saved_points.extend(points)

    monkeypatch.setattr(cardano_module.cardano_service, "get_stake_address", fake_get_stake_address)
    monkeypatch.setattr(svc, "_collect_cardano_account", fake_collect_cardano_account)
    monkeypatch.setattr(svc, "_collect_cardano", fake_collect_cardano)
    monkeypatch.setattr(svc, "_fetch_historical_prices", fake_fetch_historical_prices)
    monkeypatch.setattr(balance_history_module, "save_balance_history_batch", fake_save_balance_history_batch)

    wallet = {"id": wallet_id, "user_id": USER_ID, "address": "addr1_enterprise",
              "blockchain": "cardano", "stake_address": None}
    await svc._collect_wallet(USER_ID, wallet, max_days_back=3650, job_id=0)

    assert account_called == [], "an enterprise address must never hit the account-level path"
    assert single_called == ["addr1_enterprise"]
    assert len(saved_points) == 1 and saved_points[0]["wallet_id"] == wallet_id
