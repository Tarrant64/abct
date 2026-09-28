"""
Unit tests for ABCT-NFT-DIAG-2026-09-27 (EVM NFTs missing).

Bug 1: every Alchemy getNFTsForOwner call sent ``excludeFilters[]=SPAM``.
Alchemy now answers that with HTTP 400 on free-tier keys ("can only be used
with a payg or higher plan"), so Ethereum, Polygon, Base (and the generic EVM
chains) always showed zero NFTs. Fix: never send the parameter; drop spam
client-side from ``contract.isSpam``.

Bug 2: a failed fetch overwrote the persistent NFT cache with an empty list.
Fix: NFTs of wallets whose fetch failed are kept from the previous cache.

All HTTP and DB access is mocked: no network, no real keys, no real addresses.
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from services import alchemy_nft_utils as utils  # noqa: E402

WALLET_A = "0x" + "a" * 40
WALLET_B = "0x" + "b" * 40


def _nft(contract, token, spam=False, image="https://example.invalid/i.png"):
    return {
        "contract": {"address": contract, "isSpam": spam, "name": "C", "openSeaMetadata": {}},
        "tokenId": token,
        "name": f"N{token}",
        "image": {"cachedUrl": image},
    }


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = str(self._json)

    def json(self):
        return self._json


class RecordingClient:
    """Stands in for the shared httpx client; records query params."""

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


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def test_build_owner_params_never_sends_paid_plan_filter():
    p = utils.build_owner_params(WALLET_A)
    assert "excludeFilters[]" not in p and "excludeFilters" not in p
    assert p["owner"] == WALLET_A and p["withMetadata"] == "true"
    assert "pageKey" not in p
    assert utils.build_owner_params(WALLET_A, "k1")["pageKey"] == "k1"


def test_is_alchemy_spam_reads_contract_and_legacy_fields():
    assert utils.is_alchemy_spam({"contract": {"isSpam": True}})
    assert utils.is_alchemy_spam({"contract": {}, "spamInfo": {"isSpam": "true"}})
    assert not utils.is_alchemy_spam({"contract": {"isSpam": False}})
    assert not utils.is_alchemy_spam({"contract": {}})
    assert not utils.is_alchemy_spam(None)


def test_drop_spam_keeps_pagination_fields():
    data = {"ownedNfts": [_nft("0x1", "1"), _nft("0x2", "2", spam=True)], "pageKey": "next", "totalCount": 2}
    out = utils.drop_spam(data)
    assert [n["tokenId"] for n in out["ownedNfts"]] == ["1"]
    assert out["pageKey"] == "next" and out["totalCount"] == 2
    assert utils.drop_spam(None) is None


def test_restore_failed_wallets_only_restores_failed_owner():
    fresh = {}
    prev = [
        {"asset_id": "x_1", "wallet_address": WALLET_A.upper().replace("0X", "0x")},
        {"asset_id": "y_1", "wallet_address": WALLET_B},
    ]
    n = utils.restore_failed_wallets(fresh, prev, {WALLET_A})
    assert n == 1 and list(fresh) == ["x_1"]
    assert utils.restore_failed_wallets({}, prev, set()) == 0


# ---------------------------------------------------------------------------
# Ethereum service end-to-end (mocked)
# ---------------------------------------------------------------------------

@pytest.fixture
def eth_service(monkeypatch):
    import services.ethereum_nft as mod

    svc = mod.EthereumNFTService()
    store = {}

    async def fake_get_api_key(self, user_id=1):
        return "test-key-not-real"

    async def fake_get_all_wallets(user_id=None):
        return [
            {"blockchain": "ethereum", "address": WALLET_A},
            {"blockchain": "ethereum", "address": WALLET_B},
        ]

    async def fake_get_cache(key, user_id=None):
        return store.get(key)

    async def fake_set_cache(key, value, ttl_seconds=300, user_id=None):
        store[key] = value

    monkeypatch.setattr(mod.EthereumNFTService, "get_api_key", fake_get_api_key)
    monkeypatch.setattr(mod, "get_all_wallets", fake_get_all_wallets)
    monkeypatch.setattr(mod, "get_cache", fake_get_cache)
    monkeypatch.setattr(mod, "set_cache", fake_set_cache)
    return mod, svc, store


async def test_ethereum_request_has_no_spam_filter_and_spam_is_dropped(eth_service, monkeypatch):
    mod, svc, store = eth_service
    client = RecordingClient({
        WALLET_A: FakeResponse(200, {"ownedNfts": [_nft("0x1", "1"), _nft("0x9", "9", spam=True)]}),
        WALLET_B: FakeResponse(200, {"ownedNfts": [_nft("0x2", "2")]}),
    })
    monkeypatch.setattr(mod, "get_client", lambda *a, **k: client)

    nfts = await svc.get_all_ethereum_nfts(force_refresh=True)

    assert all("excludeFilters[]" not in c for c in client.calls)
    assert sorted(n["asset_id"] for n in nfts) == ["0x1_1", "0x2_2"]
    assert len(store[mod.ETH_NFT_CACHE_KEY]["nfts"]) == 2


async def test_ethereum_failed_wallet_keeps_previous_cache(eth_service, monkeypatch):
    mod, svc, store = eth_service
    store[mod.ETH_NFT_CACHE_KEY] = {
        "nfts": [
            {"asset_id": "0xold_7", "wallet_address": WALLET_A, "contract_address": "0xold",
             "collection": {"name": "Old", "floor_price_eth": 0, "verified": False}},
        ],
        "collections": {},
        "last_refresh": None,
    }
    paid_plan_error = FakeResponse(400, {"error": "excludeFilters can only be used with a payg or higher plan"})
    client = RecordingClient({
        WALLET_A: paid_plan_error,
        WALLET_B: FakeResponse(200, {"ownedNfts": [_nft("0x2", "2")]}),
    })
    monkeypatch.setattr(mod, "get_client", lambda *a, **k: client)

    nfts = await svc.get_all_ethereum_nfts(force_refresh=True)

    ids = sorted(n["asset_id"] for n in nfts)
    assert ids == ["0x2_2", "0xold_7"]
    assert sorted(n["asset_id"] for n in store[mod.ETH_NFT_CACHE_KEY]["nfts"]) == ids


# ---------------------------------------------------------------------------
# Polygon / Base / generic EVM share the same request builder
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("modname,cls", [
    ("services.polygon", "PolygonService"),
    ("services.base", "BaseService"),
])
async def test_polygon_and_base_requests_have_no_spam_filter(modname, cls, monkeypatch):
    import importlib

    mod = importlib.import_module(modname)
    svc = getattr(mod, cls)()
    client = RecordingClient({
        WALLET_A: FakeResponse(200, {"ownedNfts": [_nft("0x1", "1"), _nft("0x9", "9", spam=True)]}),
    })

    async def yes(*a, **k):
        return True

    async def nft_url(*a, **k):
        return "https://example.invalid/nft/v3/key"

    monkeypatch.setattr(mod, "get_client", lambda *a, **k: client)
    monkeypatch.setattr(svc, "is_configured", yes)
    monkeypatch.setattr(svc, "_get_nft_url", nft_url)

    data = await svc.get_nfts_for_owner(WALLET_A)

    assert client.calls and "excludeFilters[]" not in client.calls[0]
    assert [n["tokenId"] for n in data["ownedNfts"]] == ["1"]


def test_no_service_source_still_sends_paid_plan_filter():
    services_dir = os.path.join(BACKEND_DIR, "services")
    offenders = []
    for fn in os.listdir(services_dir):
        if fn.endswith(".py"):
            with open(os.path.join(services_dir, fn)) as fh:
                src = fh.read()
            if "'excludeFilters[]': 'SPAM'" in src or '"excludeFilters[]": "SPAM"' in src:
                offenders.append(fn)
    assert offenders == []
