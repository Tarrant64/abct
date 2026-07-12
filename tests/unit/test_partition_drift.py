"""Adversarial probe: stored sibling NOT in the Koios address set (drift).

Adopted from the P2 reviewer's demonstration (P2-FIX H1). Stored rows:
D (drifted, unused on-chain -> absent from Koios) and S (known). D sorts
lexicographically below S. Before the fix, BOTH rows claimed the orphan
credentials — an unbounded-duration double-count, because Koios never
indexes an unused address. The partition must hold: no overlap, and the
drifted row falls back to its own credential (correct — a never-used
address cannot hold positions).

Uses the REAL resolve_wallet_context + _resolve_scan_identity.
"""
import os
import sys

import bech32 as b32
import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402
import routers.defi as defi_router  # noqa: E402
import services.cardano as cardano_module  # noqa: E402
import services.defi as defi_module  # noqa: E402
from routers.defi import _resolve_scan_identity  # noqa: E402


def make_addr(payment_byte: int, stake_byte: int = 9) -> str:
    data = bytes([0x01]) + bytes([payment_byte]) * 28 + bytes([stake_byte]) * 28
    return b32.bech32_encode("addr", b32.convertbits(list(data), 8, 5))


def cred_of(payment_byte: int) -> str:
    return (bytes([payment_byte]) * 28).hex()


ALL = {make_addr(i): cred_of(i) for i in range(1, 7)}
ADDR_LIST = sorted(ALL)  # lexicographic, like the router does


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data
        self.text = str(json_data)

    def json(self):
        return self._json


class MemoryCache:
    def __init__(self):
        self.store = {}

    async def get_cache(self, key, user_id=None):
        return self.store.get((user_id, key))

    async def set_cache(self, key, value, ttl, user_id=None):
        self.store[(user_id, key)] = value


@pytest.fixture
def drift_env(monkeypatch):
    """Wire the real context/identity code to a drifted address book."""

    def _wire(koios_set, stored):
        cache = MemoryCache()
        monkeypatch.setattr(database, "get_cache", cache.get_cache)
        monkeypatch.setattr(database, "set_cache", cache.set_cache)

        class KoiosClient:
            async def post(self, url, **kwargs):
                return FakeResponse(json_data=[{"addresses": koios_set}])

            async def get(self, url, **kwargs):
                return FakeResponse(status_code=404)

        monkeypatch.setattr(defi_module, "get_client", lambda *a, **k: KoiosClient())
        monkeypatch.setattr(cardano_module, "_derive_stake_key_local",
                            lambda a: "stake1uSHARED")
        monkeypatch.setattr(defi_module.defi_service, "_get_payment_credential",
                            lambda a: ALL.get(a))

        async def fake_wallets(user_id=None):
            return [{"address": a, "blockchain": "cardano"} for a in stored]

        monkeypatch.setattr(defi_router, "get_all_wallets", fake_wallets)
        return cache

    return _wire


async def test_drift_overlap(drift_env):
    """The reviewer's probe verbatim: drifted lowest-sorting stored row."""
    D = ADDR_LIST[0]
    K = [a for a in ADDR_LIST if a != D]
    S = K[0]
    drift_env(koios_set=K, stored=[D, S])

    creds_S, _ = await _resolve_scan_identity(S, user_id=1)
    creds_D, _ = await _resolve_scan_identity(D, user_id=1)

    set_S = set(creds_S) if creds_S else {ALL[S]}
    set_D = set(creds_D) if creds_D else {ALL[D]}
    overlap = set_S & set_D
    union = set_S | set_D
    missing = set(ALL.values()) - union

    assert not overlap, "PARTITION VIOLATED: creds claimed by two rows"
    assert not missing, "PARTITION INCOMPLETE: creds claimed by no row"
    # The drifted row scans only itself; the Koios-known row is representative
    assert set_D == {ALL[D]}
    assert set_S == set(ALL.values()) - {ALL[D]}


async def test_drifted_row_self_append_is_persisted(drift_env):
    """H1(b): resolving the drifted row must persist its address into the
    shared cached context so every sibling resolves an identical context."""
    D = ADDR_LIST[0]
    K = [a for a in ADDR_LIST if a != D]
    S = K[0]
    cache = drift_env(koios_set=K, stored=[D, S])

    # S resolves first (Koios path, cached), then D self-appends
    ctx_S1 = await defi_module.defi_service.resolve_wallet_context(S)
    assert D not in ctx_S1["addresses"]

    ctx_D = await defi_module.defi_service.resolve_wallet_context(D)
    assert D in ctx_D["addresses"]
    assert D not in ctx_D["koios_addresses"]  # append never fakes chain data

    # The merge is persisted: S now sees D too — identical contexts
    ctx_S2 = await defi_module.defi_service.resolve_wallet_context(S)
    assert D in ctx_S2["addresses"]
    assert ALL[D] in ctx_S2["payment_creds"]
    assert ctx_S2["koios_addresses"] == ctx_S1["koios_addresses"]

    # And the representative now EXCLUDES the drifted stored row's cred
    creds_S, _ = await _resolve_scan_identity(S, user_id=1)
    assert ALL[D] not in creds_S


async def test_deleted_sibling_mid_ttl_creds_reclaimed(drift_env):
    """A stored sibling deleted mid-TTL: its credential becomes an orphan and
    the representative reclaims it on the next scan — no zero-count gap."""
    S = ADDR_LIST[0] if ADDR_LIST[0] in ADDR_LIST else ADDR_LIST[0]
    K = list(ADDR_LIST)  # everything chain-observed
    rep = sorted(K)[0]
    sibling = sorted(K)[1]

    # Phase 1: both stored — sibling's cred excluded from the rep's claim
    drift_env(koios_set=K, stored=[rep, sibling])
    creds_before, _ = await _resolve_scan_identity(rep, user_id=1)
    assert ALL[sibling] not in creds_before

    # Phase 2: sibling row deleted — stored set is read fresh per scan
    drift_env(koios_set=K, stored=[rep])
    creds_after, _ = await _resolve_scan_identity(rep, user_id=1)
    assert ALL[sibling] in creds_after
    assert set(creds_after) == set(ALL.values())
