"""
Regression tests for WQ-0058 (PRJ-Y acceptance case 1):

1. UNPRICED NFTs must never be summed as $0. A collection with no floor price
   is a missing fact, not a free asset: it must be excluded from every total
   and marked (priced counts / null USD), so a real 0.0 floor and a merely
   unpriced collection are distinguishable in the portfolio total
   (ABCT-NFT-FLOOR-RESEARCH-2026-09-27 recommendation).

2. The fungible ticker/decimals come from the token-registry metadata block
   (Blockfrost `/assets/{unit}` -> `metadata`, the CIP-26 off-chain registry),
   NOT from `onchain_metadata` (the CIP-25/68 on-chain block, populated mainly
   for NFTs) — ABCT-TOKEN-REGISTRY-RESEARCH-2026-09-27 finding 1a.

All offline, mocked at the boundaries: no live calls, no API keys.
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from services import nft_pricing  # noqa: E402  (stdlib only)

# The backend modules imported inside the tests below pull in httpx/fastapi/
# pydantic/aiosqlite/dotenv at import time; stub those for this module only
# when they are not installed (tests/conftest.py, offline_stubs).
pytestmark = pytest.mark.usefixtures("offline_stubs")


# ---------------------------------------------------------------------------
# 1. The shared helpers
# ---------------------------------------------------------------------------


class TestToPrice:
    def test_none_and_empty_are_unpriced(self):
        for value in (None, "", [], {}, "n/a"):
            assert nft_pricing.to_price(value) is None, value

    def test_zero_is_a_real_price(self):
        assert nft_pricing.to_price(0) == 0.0
        assert nft_pricing.to_price("0.0") == 0.0

    def test_strings_are_coerced(self):
        assert nft_pricing.to_price("1.25") == 1.25


class TestPricedUsd:
    def test_unpriced_floor_gives_none(self):
        assert nft_pricing.priced_usd(3000.0, None) is None

    def test_missing_native_price_gives_none(self):
        # a failed price lookup (0.0 from the provider) is NOT "worth zero"
        assert nft_pricing.native_price_or_none(0.0) is None
        assert nft_pricing.priced_usd(nft_pricing.native_price_or_none(0.0), 2.0) is None

    def test_real_zero_floor_is_priced(self):
        assert nft_pricing.priced_usd(3000.0, 0.0) == 0.0

    def test_priced_pair_multiplies(self):
        assert nft_pricing.priced_usd(2.0, 1.5) == 3.0


class TestCollectionFloorRollup:
    @staticmethod
    def _nft(name, floor):
        return {
            "name": f"{name} #{id(floor)}",
            "collection": {"name": name, "floor_price_eth": floor},
        }

    def test_unpriced_excluded_priced_summed(self):
        nfts = [
            self._nft("Priced", 2.0),
            self._nft("Priced", None),      # same collection priced elsewhere
            self._nft("Unpriced", None),
            self._nft("Unpriced", "junk"),  # corrupted floor row -> unpriced
            self._nft("Free", 0.0),         # a genuine 0 floor
        ]
        groups = nft_pricing.collection_floor_rollup(nfts, "floor_price_eth")

        assert groups["Priced"]["count"] == 2
        assert groups["Priced"]["priced_count"] == 1
        assert groups["Priced"]["unpriced_count"] == 1
        assert groups["Priced"]["total_native"] == 2.0

        # the whole-collection-unpriced case contributes NOTHING to any sum
        assert groups["Unpriced"]["count"] == 2
        assert groups["Unpriced"]["priced_count"] == 0
        assert groups["Unpriced"]["total_native"] == 0.0

        # a real 0.0 floor is PRICED (priced_count), not "unpriced"
        assert groups["Free"]["priced_count"] == 1
        assert groups["Free"]["unpriced_count"] == 0

    def test_missing_collection_key_is_unpriced_not_error(self):
        nfts = [{"name": "x", "collection": {}}]
        groups = nft_pricing.collection_floor_rollup(nfts, "floor_price_eth")
        assert groups["Unknown Collection"]["unpriced_count"] == 1


class TestPricedTotals:
    def test_only_complete_pairs_sum(self):
        total, priced, unpriced = nft_pricing.priced_totals(
            [2.0, 2.0, None, 2.0], [1.0, None, 1.0, 0.0]
        )
        assert total == 2.0  # 2*1.0 + 2*0.0
        assert priced == 2
        assert unpriced == 2


# ---------------------------------------------------------------------------
# 2. The per-chain service summaries honour the rule
# ---------------------------------------------------------------------------


def _evm_nft(collection, token_id, name="n"):
    return {
        "name": name,
        "token_id": token_id,
        "contract_address": "0x" + "ab" * 20,
        "image_url": "",
        "collection": collection,
        "links": {},
    }


def _patch_all(monkeypatch, service, method, value):
    async def _fake(*args, **kwargs):
        return value
    monkeypatch.setattr(service, method, _fake)


def test_ethereum_summary_excludes_unpriced(monkeypatch):
    from services.ethereum_nft import EthereumNFTService

    svc = EthereumNFTService.__new__(EthereumNFTService)  # skip __init__/API key
    svc.last_refresh = None
    nfts = [
        _evm_nft({"name": "Paid", "floor_price_eth": 1.5, "verified": True}, "1"),
        _evm_nft({"name": "Paid", "floor_price_eth": 1.5, "verified": True}, "2"),
        _evm_nft({"name": "NoFloor", "floor_price_eth": None, "verified": False}, "3"),
        _evm_nft({"name": "FreeReal", "floor_price_eth": 0.0, "verified": False}, "4"),
    ]
    _patch_all(monkeypatch, svc, "get_all_ethereum_nfts", nfts)

    import asyncio
    summary = asyncio.run(svc.get_nft_summary(user_id=1))

    # 1.5 + 1.5 + 0.0 — the NoFloor NFT adds nothing and is counted unpriced
    assert summary["total_value_eth"] == 3.0
    assert summary["total_nfts"] == 4
    assert summary["unpriced_nfts"] == 1
    by_name = {c["name"]: c for c in summary["collections"]}
    assert by_name["Paid"]["total_value_eth"] == 3.0
    assert by_name["NoFloor"]["total_value_eth"] == 0.0
    assert by_name["NoFloor"]["floor_price_eth"] is None      # null, not 0
    assert by_name["NoFloor"]["unpriced_count"] == 1
    assert by_name["FreeReal"]["floor_price_eth"] == 0.0      # a real zero
    assert by_name["FreeReal"]["unpriced_count"] == 0


def test_evm_chain_generic_summary_excludes_unpriced(monkeypatch):
    from services.evm_chain import EVMChainService

    svc = EVMChainService.__new__(EVMChainService)
    svc.native_symbol = "BNB"
    svc.last_nft_refresh = None
    nfts = [
        _evm_nft({"name": "Paid", "floor_price_bnb": 2.0, "verified": True}, "1"),
        _evm_nft({"name": "Ghost", "floor_price_bnb": None, "verified": False}, "2"),
    ]
    _patch_all(monkeypatch, svc, "get_all_nfts", nfts)

    import asyncio
    summary = asyncio.run(svc.get_nft_summary(wallets=[]))
    assert summary["total_value_bnb"] == 2.0
    assert summary["unpriced_nfts"] == 1


def test_solana_summary_never_invents_value(monkeypatch):
    from services.solana_nft import SolanaNFTService

    svc = SolanaNFTService.__new__(SolanaNFTService)
    svc.last_refresh = None
    nfts = [
        {
            "name": f"n{i}",
            "asset_id": f"asset{i}",
            "image_url": "",
            "links": {},
            "collection": {"name": "SolCole", "id": "col1", "floor_price_sol": None},
        }
        for i in range(5)
    ]
    _patch_all(monkeypatch, svc, "get_all_solana_nfts", nfts)

    import asyncio
    summary = asyncio.run(svc.get_nft_summary(user_id=1))
    # Helius gives no floors: the whole collection is UNPRICED, not "$0 of
    # holdings". It must show as 5 unpriced, 0 valued, and carry a null floor.
    assert summary["total_value_sol"] == 0.0
    assert summary["unpriced_nfts"] == 5
    col = summary["collections"][0]
    assert col["floor_price_sol"] is None
    assert col["priced_count"] == 0
    assert col["unpriced_count"] == 5


# ---------------------------------------------------------------------------
# 3. Alchemy parse: a missing floorPrice stays None, not 0
# ---------------------------------------------------------------------------


def test_alchemy_missing_floor_stays_none():
    from services.ethereum_nft import EthereumNFTService

    svc = EthereumNFTService.__new__(EthereumNFTService)
    parsed = svc._parse_nft({
        "tokenId": "7",
        "contract": {
            "address": "0x" + "cd" * 20,
            "name": "Cole",
            "openSeaMetadata": {"collectionName": "Cole"},  # NO floorPrice key
        },
        "image": {},
    }, "0xwallet")
    assert parsed["collection"]["floor_price_eth"] is None


# ---------------------------------------------------------------------------
# 4. Ticker from the registry block, not onchain_metadata
# ---------------------------------------------------------------------------


class TestRegistryTicker:
    """Blockfrost /assets/{unit} carries two blocks: `metadata` (the CIP-26
    token registry, re-exported) and `onchain_metadata` (CIP-25/68). The
    fungible ticker/decimals come from the REGISTRY block."""

    def test_registry_block_wins_over_onchain(self):
        from engine.enrichment.token_metadata_enricher import cardano_metadata_fields

        data = {
            "asset_name": "MILK",
            "metadata": {"name": "Milk Token", "ticker": "MILK", "decimals": 6},
            "onchain_metadata": {"name": "milk-nft-ish", "ticker": "WRONG"},
        }
        meta = cardano_metadata_fields(data)
        assert meta["symbol"] == "MILK"
        assert meta["decimals"] == 6
        assert meta["name"] == "Milk Token"

    def test_onchain_only_token_still_resolves(self):
        from engine.enrichment.token_metadata_enricher import cardano_metadata_fields

        data = {
            "asset_name": "SELFDESC",
            "metadata": None,                      # never registered — the
            "onchain_metadata": {"name": "Self", "ticker": "SELF", "decimals": "2"},
        }
        meta = cardano_metadata_fields(data)      # fixture shows registry null
        assert meta["symbol"] == "SELF"
        assert meta["decimals"] == 2              # string decimals coerced

    def test_registry_without_ticker_does_not_yield_wrong_onchain_value(self):
        from engine.enrichment.token_metadata_enricher import cardano_metadata_fields

        data = {
            "asset_name": "PART",
            "metadata": {"name": "Part", "decimals": 4},   # registry entry
            "onchain_metadata": {"ticker": "NFTLABEL"},    # no ticker
            # registry has no ticker -> onchain ticker is the documented fallback
        }
        meta = cardano_metadata_fields(data)
        assert meta["symbol"] == "NFTLABEL"
        assert meta["decimals"] == 4               # decimals from the registry

    def test_nothing_registered_falls_back_to_asset_name(self):
        from engine.enrichment.token_metadata_enricher import cardano_metadata_fields

        meta = cardano_metadata_fields({"asset_name": "RAWHEX", "metadata": None,
                                        "onchain_metadata": None})
        assert meta["name"] == "RAWHEX"
        assert meta["symbol"] == ""
        assert meta["decimals"] == 0

    def test_bad_string_decimals_become_zero(self):
        from engine.enrichment.token_metadata_enricher import cardano_metadata_fields

        meta = cardano_metadata_fields(
            {"asset_name": "X", "metadata": {"decimals": "lots"}, "onchain_metadata": {}})
        assert meta["decimals"] == 0


def test_asset_metadata_keeps_blocks_separate():
    """services.cardano.get_asset_metadata must surface the registry block
    separately from onchain_metadata so ticker readers can prefer it."""
    import asyncio
    import services.cardano as cardano_module
    payload = {
        "policy_id": "p" * 56,
        "asset_name": "TOK",
        "fingerprint": "asset1xx",
        "quantity": "100",
        "metadata": {"name": "Tok", "ticker": "TOK", "decimals": 5},
        "onchain_metadata": {"name": "tok-image", "image": "ipfs://x"},
    }

    class FakeResponse:
        status_code = 200

        def json(self):
            return payload

    async def fake_fetch(*args, **kwargs):
        return FakeResponse()

    async def fake_headers():
        return {}

    svc = cardano_module.CardanoService()
    import unittest.mock as mock
    with mock.patch.object(cardano_module, "blockfrost_fetch", fake_fetch), \
         mock.patch.object(svc, "_get_blockfrost_headers", fake_headers):
        result = asyncio.run(svc.get_asset_metadata("p" * 56 + "544f4b"))

    assert result["registry_metadata"]["ticker"] == "TOK"
    assert result["registry_metadata"]["decimals"] == 5
    assert result["onchain_metadata"]["image"] == "ipfs://x"
    # the merged view now PREFERS the registry block (was onchain-first)
    assert result["metadata"]["ticker"] == "TOK"


# ---------------------------------------------------------------------------
# 5. The Ethereum list endpoint end-to-end (aggregation through the router)
# ---------------------------------------------------------------------------


def test_ethereum_list_endpoint_excludes_unpriced(monkeypatch):
    """GET /nfts/ethereum: one priced (2 ETH), one unpriced, one genuine 0.

    total_value_usd must be 2 * price — the unpriced NFT must not add 0 as a
    "valued" NFT, and it must carry floor_price_usd None (marked unpriced).
    """
    import asyncio
    import routers.nfts as nfts_module

    def nft(coll, tid, name):
        return {"name": name, "token_id": tid, "contract_address": "0xaa",
                "image_url": "", "collection": dict(coll), "links": {}}

    nfts = [
        nft({"name": "Paid", "floor_price_eth": 2.0, "verified": True}, "1", "a"),
        nft({"name": "Ghost", "floor_price_eth": None, "verified": False}, "2", "b"),
        nft({"name": "FreeReal", "floor_price_eth": 0.0, "verified": False}, "3", "c"),
    ]

    async def fake_all(user_id=None, force_refresh=False):
        return [dict(n, collection=dict(n["collection"])) for n in nfts]

    async def fake_configured():
        return True

    async def fake_price(symbol):
        return 3000.0

    async def fake_user(uid):
        return "someone"

    async def fake_demo(username):
        return False

    monkeypatch.setattr(nfts_module.ethereum_nft_service, "get_all_ethereum_nfts", fake_all)
    monkeypatch.setattr(nfts_module.ethereum_nft_service, "is_configured", fake_configured)
    monkeypatch.setattr(nfts_module.ethereum_nft_service, "last_refresh", None)
    monkeypatch.setattr(nfts_module.pricing_service, "get_price", fake_price)
    monkeypatch.setattr(nfts_module, "get_username_by_user_id", fake_user)
    monkeypatch.setattr(nfts_module, "is_demo_user", fake_demo)

    result = asyncio.run(nfts_module.get_ethereum_nfts(user_id=1))

    assert result["total_value_usd"] == 6000.0   # 2.0 ETH priced; ghost adds nothing
    assert result["total_value_eth"] == 2.0
    assert result["valued_count"] == 2           # paid + a genuine 0 (both priced)
    assert result["unpriced_nfts"] == 1
    by_coll = {n["collection"]["name"]: n for n in result["nfts"]}
    assert by_coll["Ghost"]["floor_price_usd"] is None    # marked unpriced
    assert by_coll["FreeReal"]["floor_price_usd"] == 0.0  # real zero
    # unpriced sort last
    assert result["nfts"][-1]["collection"]["name"] == "Ghost"


def test_failed_native_price_never_makes_priced_nfts_zero(monkeypatch):
    """A pricing-provider failure (get_price -> 0) marks NFTs unpriced; it
    must not present priced floors as $0 holdings."""
    import asyncio
    import routers.nfts as nfts_module

    nft = {"name": "a", "token_id": "1", "contract_address": "0xaa",
           "image_url": "", "links": {},
           "collection": {"name": "Paid", "floor_price_eth": 2.0, "verified": True}}

    async def fake_all(user_id=None, force_refresh=False):
        return [dict(nft, collection=dict(nft["collection"]))]

    async def fake_configured():
        return True

    async def fake_price(symbol):
        return 0.0     # provider failed

    async def fake_user(uid):
        return "someone"

    async def fake_demo(username):
        return False

    monkeypatch.setattr(nfts_module.ethereum_nft_service, "get_all_ethereum_nfts", fake_all)
    monkeypatch.setattr(nfts_module.ethereum_nft_service, "is_configured", fake_configured)
    monkeypatch.setattr(nfts_module.ethereum_nft_service, "last_refresh", None)
    monkeypatch.setattr(nfts_module.pricing_service, "get_price", fake_price)
    monkeypatch.setattr(nfts_module, "get_username_by_user_id", fake_user)
    monkeypatch.setattr(nfts_module, "is_demo_user", fake_demo)

    result = asyncio.run(nfts_module.get_ethereum_nfts(user_id=1))
    assert result["nfts"][0]["floor_price_usd"] is None
    assert result["total_value_usd"] == 0.0
    assert result["unpriced_nfts"] == 1

