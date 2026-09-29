"""
Regression tests for ABCT-IAGON-SCANSTATE-FIX-2026-09-28.

Context: PR #13 (fix/system-cache-null-user-upsert) fixes the system-wide
cache so a system-wide read returns the newest row instead of the oldest.
That turns on the Iagon staking scan's *incremental* path in practice (on
main today the scan state is effectively never read back, so every scan is
a full rescan and any transient UTxO-fetch failure self-heals on the next
call).

Both Iagon scan implementations --
services/defi_protocols/cardano/iagon.py (IagonAdapter) and
services/defi.py (DeFiService._get_iagon_staking_inner) -- fetch each
transaction's UTxOs in parallel and `continue` past any tx whose fetch
failed (HTTP error or exception), silently omitting that tx's IAG flow from
the totals for *this* call. Before this fix, `last_block_height` was still
advanced to the highest block among the *successful* fetches and the scan
state was always saved. If a later transaction (higher block) succeeded
while an earlier one failed, the next incremental scan resumed after the
failed transaction's block and never retried it -- the skipped flow was
gone for good, and every following scan renewed the 7-day TTL on that
wrong total.

The fix: if any UTxO fetch failed during a scan, do not save/advance the
scan state for that run at all. The previous state (or lack of one) is left
untouched, so the next call retries the same range from the same starting
point -- exactly like main's current (accidental) full-rescan behavior.

Covered, for BOTH implementations:
1. All UTxO fetches succeed -> scan state is saved (unchanged behavior).
2. One UTxO fetch fails -> scan state is NOT saved this run, and the next
   scan (which now has no saved state to resume from) does a full rescan
   that includes the previously-skipped transaction.
3. Follow-up from ABCT-PR13-16-REVIEW-2026-09-28 (#14 note 1): SCAN_STATE_VERSION
   was bumped 5->6 in both implementations so the first scan after deploy
   discards any pre-existing v5 row rather than trusting it as a resume
   point. A v5 row saved by `main` before this fix may itself already be
   "holed" (missing a transaction the pre-fix bug silently skipped) --
   version-gating forces one full rescan to repair it, instead of letting
   #13's newest-row read make that holed row the permanent resume point.
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402
import services.defi as defi_module  # noqa: E402
import services.defi_protocols.cardano.iagon as iagon_module  # noqa: E402
from services.defi import DeFiService  # noqa: E402
from services.defi_protocols.cardano.iagon import (  # noqa: E402
    IagonAdapter,
    IAGON_IAG_ASSET,
    IAGON_OPERATOR_STAKING_ADDRESS,
)

ADDRESS = "addr1qtesticagonscanstatefix000000000000000000000000000000000000"
SCAN_KEY = f"iagon_scan_state_{ADDRESS}"

TX1 = {"tx_hash": "a1" * 32, "block_height": 100}
TX2 = {"tx_hash": "b2" * 32, "block_height": 101}


def _iag_output(address, quantity):
    return {
        "address": address,
        "amount": [{"unit": IAGON_IAG_ASSET, "quantity": str(quantity)}],
    }


def _iag_input(address, quantity):
    return _iag_output(address, quantity)


# tx1: 1,000,000 (1 IAG) deposited into the operator staking contract.
TX1_UTXOS = {
    "inputs": [_iag_input("addr1_user_wallet", 1_000_000)],
    "outputs": [_iag_output(IAGON_OPERATOR_STAKING_ADDRESS, 1_000_000)],
}

# tx2: 2,000,000 (2 IAG) deposited into the operator staking contract.
TX2_UTXOS = {
    "inputs": [_iag_input("addr1_user_wallet", 2_000_000)],
    "outputs": [_iag_output(IAGON_OPERATOR_STAKING_ADDRESS, 2_000_000)],
}

UTXOS_BY_HASH = {TX1["tx_hash"]: TX1_UTXOS, TX2["tx_hash"]: TX2_UTXOS}


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data

    def json(self):
        return self._json


class FakeCache:
    """In-memory stand-in for database.get_cache/set_cache (system-wide,
    user_id=None only -- all the Iagon scan-state calls use)."""

    def __init__(self):
        self.store = {}
        self.set_calls = []

    async def get_cache(self, key, user_id=None):
        return self.store.get(key)

    async def set_cache(self, key, value, ttl_seconds=300, user_id=None):
        self.set_calls.append((key, value))
        self.store[key] = value

    async def clear_cache(self, key_pattern=None, user_id=None):
        self.store.clear()


def make_blockfrost_fetch(fail_hashes):
    """Fake blockfrost_fetch covering /addresses/{addr}/transactions and
    /txs/{hash}/utxos. fail_hashes: tx hashes whose UTxO fetch returns a
    500 (simulating a transient Blockfrost failure)."""

    async def _fake(path, *, method="GET", timeout=30.0, headers=None, params=None, **kwargs):
        if path == f"/addresses/{ADDRESS}/transactions":
            page = (params or {}).get("page", 1)
            from_block = (params or {}).get("from")
            if page != 1:
                return FakeResponse(status_code=200, json_data=[])
            txs = [TX1, TX2]
            if from_block is not None:
                txs = [t for t in txs if t["block_height"] >= int(from_block)]
            return FakeResponse(status_code=200, json_data=txs)

        if path.startswith("/txs/") and path.endswith("/utxos"):
            tx_hash = path.split("/")[2]
            if tx_hash in fail_hashes:
                return FakeResponse(status_code=500, json_data=None)
            return FakeResponse(status_code=200, json_data=UTXOS_BY_HASH[tx_hash])

        raise AssertionError(f"unexpected blockfrost_fetch path: {path}")

    return _fake


@pytest.fixture
def fake_cache(monkeypatch):
    cache = FakeCache()
    monkeypatch.setattr(database, "get_cache", cache.get_cache)
    monkeypatch.setattr(database, "set_cache", cache.set_cache)
    return cache


def _install_iagon_adapter_fakes(monkeypatch, fail_hashes):
    monkeypatch.setattr(iagon_module, "blockfrost_fetch", make_blockfrost_fetch(fail_hashes))

    async def fake_headers():
        return {"project_id": "test-key-not-real"}

    monkeypatch.setattr(iagon_module, "get_blockfrost_headers", fake_headers)


def _install_defi_service_fakes(monkeypatch, svc, fail_hashes):
    monkeypatch.setattr(defi_module, "blockfrost_fetch", make_blockfrost_fetch(fail_hashes))

    async def fake_headers():
        return {"project_id": "test-key-not-real"}

    monkeypatch.setattr(svc, "_get_headers", fake_headers)


# ---------------------------------------------------------------------------
# IagonAdapter (services/defi_protocols/cardano/iagon.py)
# ---------------------------------------------------------------------------

class TestIagonAdapterScanState:
    @pytest.mark.asyncio
    async def test_success_saves_scan_state_as_before(self, monkeypatch, fake_cache):
        """Baseline: no failures -> state is saved, behavior unchanged."""
        _install_iagon_adapter_fakes(monkeypatch, fail_hashes=set())
        adapter = IagonAdapter()

        positions = await adapter.detect_positions(ADDRESS)

        assert len(positions) == 1
        assert positions[0].amount == pytest.approx(3.0)  # 1 + 2 IAG

        assert SCAN_KEY in fake_cache.store
        saved = fake_cache.store[SCAN_KEY]
        assert saved["last_block_height"] == 101
        assert saved["staking_deposits"] == 3_000_000

    @pytest.mark.asyncio
    async def test_failed_fetch_does_not_advance_saved_state(self, monkeypatch, fake_cache):
        """tx1 (block 100) fails, tx2 (block 101) succeeds. The scan must
        NOT save state that would skip tx1 forever."""
        _install_iagon_adapter_fakes(monkeypatch, fail_hashes={TX1["tx_hash"]})
        adapter = IagonAdapter()

        positions = await adapter.detect_positions(ADDRESS)

        # This call's own result only reflects what it could fetch (tx2).
        assert len(positions) == 1
        assert positions[0].amount == pytest.approx(2.0)

        # No scan state was persisted -- the failure must not be baked in.
        assert SCAN_KEY not in fake_cache.store
        assert fake_cache.set_calls == []

    @pytest.mark.asyncio
    async def test_next_scan_retries_and_includes_previously_failed_tx(
        self, monkeypatch, fake_cache
    ):
        """After a scan with a failure (nothing saved), a later scan where
        everything succeeds must do a full rescan (no from_block to resume
        from) and end up with BOTH transactions counted -- proving the
        failed transaction is retried rather than lost."""
        _install_iagon_adapter_fakes(monkeypatch, fail_hashes={TX1["tx_hash"]})
        adapter = IagonAdapter()
        first = await adapter.detect_positions(ADDRESS)
        assert first[0].amount == pytest.approx(2.0)
        assert SCAN_KEY not in fake_cache.store

        # Second scan: Blockfrost is healthy now.
        _install_iagon_adapter_fakes(monkeypatch, fail_hashes=set())
        second = await adapter.detect_positions(ADDRESS)

        assert len(second) == 1
        assert second[0].amount == pytest.approx(3.0)  # tx1 + tx2, not just tx2
        assert fake_cache.store[SCAN_KEY]["staking_deposits"] == 3_000_000
        assert fake_cache.store[SCAN_KEY]["last_block_height"] == 101

    @pytest.mark.asyncio
    async def test_stale_v5_row_is_ignored_and_fully_rescanned(self, monkeypatch, fake_cache):
        """SCAN_STATE_VERSION was bumped 5->6 specifically so a pre-existing
        v5 row left by main before this deploy -- which may itself have
        silently skipped a transaction due to the bug this PR fixes -- is
        never trusted as a resume point. Seed a v5 row shaped exactly like
        that: last_block_height=101 (past tx1's block 100) but
        staking_deposits only reflects tx2, as if tx1's UTxO fetch had
        failed on some prior scan and state was (incorrectly, pre-fix)
        still saved. A v6-aware scan must discard it, do a full rescan
        (from_block=None), and recover tx1."""
        fake_cache.store[SCAN_KEY] = {
            "version": 5,
            "staking_deposits": 2_000_000,  # legacy: only tx2 (2 IAG) counted
            "staking_withdrawals": 0,
            "total_rewards": 0,
            "last_block_height": 101,  # a v5-trusting resume would skip tx1 (block 100) forever
        }
        _install_iagon_adapter_fakes(monkeypatch, fail_hashes=set())
        adapter = IagonAdapter()

        positions = await adapter.detect_positions(ADDRESS)

        # Full rescan recovers tx1 (1 IAG) + tx2 (2 IAG) = 3 IAG, not the
        # legacy 2 IAG a trusted v5 resume-from-101 would have stayed at.
        assert len(positions) == 1
        assert positions[0].amount == pytest.approx(3.0)

        saved = fake_cache.store[SCAN_KEY]
        assert saved["version"] == 6
        assert saved["staking_deposits"] == 3_000_000
        assert saved["last_block_height"] == 101


# ---------------------------------------------------------------------------
# DeFiService._get_iagon_staking_inner (services/defi.py)
# ---------------------------------------------------------------------------

class TestDeFiServiceIagonScanState:
    @pytest.fixture
    def service(self):
        return DeFiService()

    @pytest.mark.asyncio
    async def test_success_saves_scan_state_as_before(self, monkeypatch, fake_cache, service):
        _install_defi_service_fakes(monkeypatch, service, fail_hashes=set())

        result = await service.get_iagon_staking(ADDRESS)

        assert result is not None
        assert result["total_staked_iag"] == pytest.approx(3.0)
        assert SCAN_KEY in fake_cache.store
        assert fake_cache.store[SCAN_KEY]["last_block_height"] == 101
        assert fake_cache.store[SCAN_KEY]["staking_deposits"] == 3_000_000

    @pytest.mark.asyncio
    async def test_failed_fetch_does_not_advance_saved_state(
        self, monkeypatch, fake_cache, service
    ):
        _install_defi_service_fakes(monkeypatch, service, fail_hashes={TX1["tx_hash"]})

        result = await service.get_iagon_staking(ADDRESS)

        assert result is not None
        assert result["total_staked_iag"] == pytest.approx(2.0)
        assert SCAN_KEY not in fake_cache.store
        assert fake_cache.set_calls == []

    @pytest.mark.asyncio
    async def test_next_scan_retries_and_includes_previously_failed_tx(
        self, monkeypatch, fake_cache, service
    ):
        _install_defi_service_fakes(monkeypatch, service, fail_hashes={TX1["tx_hash"]})
        first = await service.get_iagon_staking(ADDRESS)
        assert first["total_staked_iag"] == pytest.approx(2.0)
        assert SCAN_KEY not in fake_cache.store

        _install_defi_service_fakes(monkeypatch, service, fail_hashes=set())
        second = await service.get_iagon_staking(ADDRESS)

        assert second["total_staked_iag"] == pytest.approx(3.0)
        assert fake_cache.store[SCAN_KEY]["staking_deposits"] == 3_000_000
        assert fake_cache.store[SCAN_KEY]["last_block_height"] == 101

    @pytest.mark.asyncio
    async def test_stale_v5_row_is_ignored_and_fully_rescanned(
        self, monkeypatch, fake_cache, service
    ):
        """Same v6 legacy-row guarantee as
        TestIagonAdapterScanState.test_stale_v5_row_is_ignored_and_fully_rescanned,
        for the DeFiService copy of the scan."""
        fake_cache.store[SCAN_KEY] = {
            "version": 5,
            "staking_deposits": 2_000_000,  # legacy: only tx2 (2 IAG) counted
            "staking_withdrawals": 0,
            "total_rewards": 0,
            "last_block_height": 101,  # a v5-trusting resume would skip tx1 (block 100) forever
        }
        _install_defi_service_fakes(monkeypatch, service, fail_hashes=set())

        result = await service.get_iagon_staking(ADDRESS)

        assert result is not None
        assert result["total_staked_iag"] == pytest.approx(3.0)
        saved = fake_cache.store[SCAN_KEY]
        assert saved["version"] == 6
        assert saved["staking_deposits"] == 3_000_000
        assert saved["last_block_height"] == 101
