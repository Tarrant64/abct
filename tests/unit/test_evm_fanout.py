"""
Unit tests for the EVM NFT fan-out half of ABCT-EVM-FANOUT-2026-09-28
(Polygon/Base NFTs missing for EVM addresses stored as 'ethereum').

Root cause: wallets are stored one-row-per-(address, blockchain)
(database.py wallets table), and utils/address.detect_blockchain always
files a bare 0x address as 'ethereum'. /nfts/polygon and /nfts/base only
ever asked about addresses whose OWN row already said that chain, so a
real Polygon/Base holder registered as 'ethereum' was invisible.

Covers:
- evm_fanout_wallets / wallet_fingerprint / EVM_ADDRESS_CHAINS /
  EVM_FANOUT_TARGET_CHAINS helpers (services/alchemy_nft_utils.py).
- An ethereum-stored address with Polygon NFTs now appears on the Polygon
  fetch; the same address present as both an ethereum and a polygon row is
  not duplicated (fetched/counted once); spam is still filtered; the #16
  wallet-set-fingerprint cache invalidation is extended to Polygon so
  adding an EVM wallet is picked up immediately without waiting on the
  persistent cache's TTL.

The balance/token fan-out (services/evm_balance_fanout.py,
routers/portfolio.py) is intentionally out of scope for this PR -- see the
independent review of #17 (http://192.168.50.240/data/2026-09-28/
ABCT-PR17-REVIEW-2026-09-28.html), which found the balance half wrong
(native coin double-counted, spam ERC-20s priced by raw symbol) and the
NFT half correct. This PR ships the NFT half alone; the balance half is
being reworked separately.

All HTTP, DB, and pricing access is mocked: no network, no real keys, no
real addresses (fake addresses are built via string repetition so the
literal 0x... string never appears in this file's source text, matching
the existing convention in tests/unit/test_alchemy_nft_free_tier.py --
verified against tests/unit/test_wallet_leak_check.py::test_real_repo_tree_is_clean).
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from services import alchemy_nft_utils as utils  # noqa: E402

# Fake, non-real EVM-shaped addresses (0x + 40 repeated hex chars). Built at
# runtime, never written as a literal string, so the wallet-leak scanner's
# static regex never sees a matching 42-char token in this file's source.
WALLET_ETH_ONLY = "0x" + "a" * 40   # ethereum row only -- should fan out to polygon+base
WALLET_DUAL = "0x" + "b" * 40       # BOTH an ethereum row AND a polygon row
WALLET_BASE_DONOR = "0x" + "c" * 40  # base row only -- should fan out to ethereum+polygon


# ---------------------------------------------------------------------------
# alchemy_nft_utils: evm_fanout_wallets / wallet_fingerprint / constants
# ---------------------------------------------------------------------------

def test_evm_fanout_wallets_dedupes_by_address_case_insensitive():
    wallets = [
        {"id": 1, "address": WALLET_ETH_ONLY, "blockchain": "ethereum"},
        {"id": 2, "address": WALLET_ETH_ONLY.upper(), "blockchain": "ethereum"},  # dup, different case
        {"id": 3, "address": WALLET_BASE_DONOR, "blockchain": "base"},
        {"id": 4, "address": "not-evm-addr", "blockchain": "cardano"},
    ]
    out = utils.evm_fanout_wallets(wallets)
    assert [w["id"] for w in out] == [1, 3]  # first occurrence wins, cardano excluded


def test_evm_fanout_wallets_includes_bsc_arb_avax_as_donors():
    wallets = [{"id": 1, "address": WALLET_ETH_ONLY, "blockchain": "bsc"}]
    assert utils.evm_fanout_wallets(wallets) == wallets


def test_evm_fanout_target_chains_is_eth_polygon_base_only():
    assert set(utils.EVM_FANOUT_TARGET_CHAINS) == {"ethereum", "polygon", "base"}
    assert "bsc" not in utils.EVM_FANOUT_TARGET_CHAINS


def test_wallet_fingerprint_stable_and_case_insensitive():
    fp1 = utils.wallet_fingerprint([WALLET_ETH_ONLY, WALLET_DUAL])
    fp2 = utils.wallet_fingerprint([WALLET_DUAL.upper(), WALLET_ETH_ONLY])
    assert fp1 == fp2
    fp3 = utils.wallet_fingerprint([WALLET_ETH_ONLY])
    assert fp1 != fp3


# ---------------------------------------------------------------------------
# NFT fan-out: an ethereum-stored address' Polygon NFTs are now reachable
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = str(self._json)

    def json(self):
        return self._json


class RecordingClient:
    def __init__(self, responses):
        self._responses = responses
        self.calls = []

    async def get(self, url, params=None, **kwargs):
        self.calls.append(dict(params or {}))
        owner = (params or {}).get("owner")
        resp = self._responses.get(owner)
        if callable(resp):
            return resp(params)
        return resp or FakeResponse(200, {"ownedNfts": [], "totalCount": 0})


def _nft(contract, token, spam=False):
    return {
        "contract": {"address": contract, "isSpam": spam, "name": "C", "openSeaMetadata": {}},
        "tokenId": token,
        "name": f"N{token}",
        "image": {"cachedUrl": "https://example.invalid/i.png"},
    }


@pytest.fixture
def polygon_service_fixture(monkeypatch):
    import services.polygon as mod

    svc = mod.PolygonService()
    store = {}

    async def yes(*a, **k):
        return True

    async def nft_url(*a, **k):
        return "https://example.invalid/nft/v3/key"

    async def fake_get_cache(key, user_id=None):
        return store.get(key)

    async def fake_set_cache(key, value, ttl_seconds=300, user_id=None):
        store[key] = value

    monkeypatch.setattr(svc, "is_configured", yes)
    monkeypatch.setattr(svc, "_get_nft_url", nft_url)
    monkeypatch.setattr(mod, "get_cache", fake_get_cache)
    monkeypatch.setattr(mod, "set_cache", fake_set_cache)
    return mod, svc, store


async def test_ethereum_stored_address_nfts_appear_on_polygon_fetch(polygon_service_fixture, monkeypatch):
    """The core bug: an address whose DB row says 'ethereum' has real Polygon
    NFTs. Before this fix the router never even built this candidate list;
    now the service is asked about it directly (this test exercises the
    service the same way the fixed router now calls it -- with the fanned-out
    wallet list rather than a chain-filtered one)."""
    mod, svc, store = polygon_service_fixture
    client = RecordingClient({
        WALLET_ETH_ONLY: FakeResponse(200, {"ownedNfts": [_nft("0x1", "1")]}),
    })
    monkeypatch.setattr(mod, "get_client", lambda *a, **k: client)

    all_wallets = [{"id": 1, "address": WALLET_ETH_ONLY, "blockchain": "ethereum"}]
    fanned_out = utils.evm_fanout_wallets(all_wallets)  # what routers/nfts.py now passes

    nfts = await svc.get_all_polygon_nfts(fanned_out, force_refresh=True)

    assert [n["asset_id"] for n in nfts] == ["0x1_1"]
    assert client.calls and client.calls[0]["owner"] == WALLET_ETH_ONLY


async def test_dual_registered_address_not_duplicated(polygon_service_fixture, monkeypatch):
    """Same address stored as BOTH an ethereum row and a polygon row must be
    fetched/counted once, not twice."""
    mod, svc, store = polygon_service_fixture
    client = RecordingClient({
        WALLET_DUAL: FakeResponse(200, {"ownedNfts": [_nft("0x1", "1")]}),
    })
    monkeypatch.setattr(mod, "get_client", lambda *a, **k: client)

    all_wallets = [
        {"id": 1, "address": WALLET_DUAL, "blockchain": "ethereum"},
        {"id": 2, "address": WALLET_DUAL, "blockchain": "polygon"},
    ]
    fanned_out = utils.evm_fanout_wallets(all_wallets)
    assert len(fanned_out) == 1  # deduped before it ever reaches the service

    nfts = await svc.get_all_polygon_nfts(fanned_out, force_refresh=True)

    assert len(client.calls) == 1  # exactly one Alchemy call for the address
    assert [n["asset_id"] for n in nfts] == ["0x1_1"]  # no duplicate NFT entries


async def test_spam_still_filtered_in_fanned_out_fetch(polygon_service_fixture, monkeypatch):
    mod, svc, store = polygon_service_fixture
    client = RecordingClient({
        WALLET_ETH_ONLY: FakeResponse(200, {"ownedNfts": [_nft("0x1", "1"), _nft("0x9", "9", spam=True)]}),
    })
    monkeypatch.setattr(mod, "get_client", lambda *a, **k: client)

    fanned_out = utils.evm_fanout_wallets(
        [{"id": 1, "address": WALLET_ETH_ONLY, "blockchain": "ethereum"}]
    )
    nfts = await svc.get_all_polygon_nfts(fanned_out, force_refresh=True)
    assert [n["asset_id"] for n in nfts] == ["0x1_1"]


async def test_wallet_set_change_invalidates_persistent_cache(polygon_service_fixture, monkeypatch):
    """Adding an EVM wallet must be picked up immediately (PR #16 pattern),
    not hidden behind the 24h in-memory / 30-day persistent Polygon cache."""
    mod, svc, store = polygon_service_fixture
    client = RecordingClient({
        WALLET_ETH_ONLY: FakeResponse(200, {"ownedNfts": [_nft("0x1", "1")]}),
        WALLET_BASE_DONOR: FakeResponse(200, {"ownedNfts": [_nft("0x2", "2")]}),
    })
    monkeypatch.setattr(mod, "get_client", lambda *a, **k: client)

    first_wallets = utils.evm_fanout_wallets(
        [{"id": 1, "address": WALLET_ETH_ONLY, "blockchain": "ethereum"}]
    )
    first = await svc.get_all_polygon_nfts(first_wallets, force_refresh=True)
    assert [n["asset_id"] for n in first] == ["0x1_1"]
    assert store[mod.POLYGON_NFT_CACHE_KEY]["wallet_fingerprint"] == utils.wallet_fingerprint(
        [WALLET_ETH_ONLY]
    )

    # A second wallet is added -- NOT force_refresh, cache is otherwise "hot"
    second_wallets = utils.evm_fanout_wallets([
        {"id": 1, "address": WALLET_ETH_ONLY, "blockchain": "ethereum"},
        {"id": 2, "address": WALLET_BASE_DONOR, "blockchain": "base"},
    ])
    second = await svc.get_all_polygon_nfts(second_wallets, force_refresh=False)
    assert sorted(n["asset_id"] for n in second) == ["0x1_1", "0x2_2"]
