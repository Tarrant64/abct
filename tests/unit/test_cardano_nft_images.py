"""
Unit tests for ABCT-NFT-DIAG-2026-09-27 (Cardano NFTs shown without images).

GET /nfts, which feeds the /next NFT page, never returned an image URL for
Cardano NFTs, so every card showed a placeholder. The fix gives each NFT an
``image_url`` from its resolved on-chain metadata image, resolving unknown
ones in a background task that saves them into the user's NFT cache.

HTTP, DB and cache access are all mocked. No network, no real keys or
addresses. The asset ids and IPFS CIDs are synthetic.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import services.nft as nft_mod  # noqa: E402

POLICY = "ab" * 28
ASSET_1 = POLICY + "4e46543031"          # "NFT01"
ASSET_2 = POLICY + "4e46543032"          # "NFT02"
ASSET_CIP68 = POLICY + "000de140" + "4e4654"  # CIP-68 (222) user token
CID = "Qm" + "x" * 44


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json


@pytest.fixture
def svc():
    return nft_mod.NFTService()


@pytest.fixture
def cache_store(monkeypatch):
    """In-memory stand-in for the cache table (user-scoped)."""
    store = {}

    async def fake_get_stale_cache(key, user_id=None):
        row = store.get((user_id, key))
        return (row["value"], row["expires_at"]) if row else (None, None)

    async def fake_set_cache(key, value, ttl_seconds=300, user_id=None):
        store[(user_id, key)] = {
            "value": value,
            "expires_at": (datetime.now() + timedelta(seconds=ttl_seconds)).isoformat(),
            "ttl": ttl_seconds,
        }

    monkeypatch.setattr(nft_mod, "get_stale_cache", fake_get_stale_cache)
    monkeypatch.setattr(nft_mod, "set_cache", fake_set_cache)
    return store


# ---------------------------------------------------------------------------
# attach_image_urls
# ---------------------------------------------------------------------------

def test_attach_sets_image_url_and_schedules_only_unknown(svc, monkeypatch):
    scheduled = []
    monkeypatch.setattr(svc, "_schedule_image_backfill", lambda uid, ids: scheduled.append((uid, list(ids))) or True)
    nfts = [
        {"asset_id": ASSET_1, "image": "https://ipfs.io/ipfs/" + CID},
        {"asset_id": ASSET_2},
        {"asset_id": ASSET_CIP68, "image_checked": True},  # looked up before, no image
    ]
    svc.attach_image_urls(nfts, user_id=1)

    assert nfts[0]["image_url"] == "https://ipfs.io/ipfs/" + CID
    assert nfts[1]["image_url"] is None and nfts[2]["image_url"] is None
    assert scheduled == [(1, [ASSET_2])]


def test_attach_without_user_does_not_schedule(svc, monkeypatch):
    scheduled = []
    monkeypatch.setattr(svc, "_schedule_image_backfill", lambda uid, ids: scheduled.append(ids))
    svc.attach_image_urls([{"asset_id": ASSET_1}], user_id=None)
    assert scheduled == []


async def test_only_one_backfill_task_runs_at_a_time(svc, monkeypatch):
    gate = asyncio.Event()

    async def slow_backfill(user_id, ids):
        await gate.wait()
        return {}

    monkeypatch.setattr(svc, "_backfill_images", slow_backfill)
    assert svc._schedule_image_backfill(1, [ASSET_1]) is True
    assert svc._schedule_image_backfill(1, [ASSET_2]) is False
    gate.set()
    await svc._image_backfill_task


# ---------------------------------------------------------------------------
# background resolution merges into the persisted cache
# ---------------------------------------------------------------------------

async def test_backfill_merges_images_and_keeps_expiry(svc, cache_store, monkeypatch):
    cache_store[(1, nft_mod.NFT_CACHE_KEY)] = {
        "value": {
            "nfts": [
                {"asset_id": ASSET_1, "price_ada": 12.0},
                {"asset_id": ASSET_2, "price_ada": None},
                {"asset_id": ASSET_CIP68},  # added by a refresh meanwhile, not in this batch
            ],
            "collections": {},
            "last_refresh": "2026-09-27T00:00:00",
        },
        "expires_at": (datetime.now() + timedelta(days=10)).isoformat(),
    }

    async def fake_resolve(asset_id):
        return {"%s" % ASSET_1: "https://ipfs.io/ipfs/" + CID}.get(asset_id)

    monkeypatch.setattr(svc, "_fetch_nft_image_url", fake_resolve)

    results = await svc._backfill_images(1, [ASSET_1, ASSET_2])

    assert results == {ASSET_1: "https://ipfs.io/ipfs/" + CID, ASSET_2: None}
    row = cache_store[(1, nft_mod.NFT_CACHE_KEY)]
    by_id = {n["asset_id"]: n for n in row["value"]["nfts"]}
    assert by_id[ASSET_1]["image"].endswith(CID) and by_id[ASSET_1]["image_checked"] is True
    assert by_id[ASSET_1]["price_ada"] == 12.0
    assert "image" not in by_id[ASSET_2] and by_id[ASSET_2]["image_checked"] is True
    assert "image_checked" not in by_id[ASSET_CIP68]
    # expiry preserved (~10 days), not reset to the 30-day default
    assert 9 * 86400 < row["ttl"] <= 10 * 86400


async def test_backfill_survives_resolver_errors(svc, cache_store, monkeypatch):
    cache_store[(1, nft_mod.NFT_CACHE_KEY)] = {
        "value": {"nfts": [{"asset_id": ASSET_1}]},
        "expires_at": (datetime.now() + timedelta(days=1)).isoformat(),
    }

    async def boom(asset_id):
        raise RuntimeError("provider down")

    monkeypatch.setattr(svc, "_fetch_nft_image_url", boom)
    results = await svc._backfill_images(1, [ASSET_1])
    assert results == {ASSET_1: None}


# ---------------------------------------------------------------------------
# resolver: on-chain metadata from a Blockfrost-compatible backend
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("metadata,expected", [
    ({"name": "N", "image": "ipfs://" + CID}, "https://ipfs.io/ipfs/" + CID),
    ({"name": "N", "image": ["ipfs://", CID]}, "https://ipfs.io/ipfs/" + CID),
    ({"name": "N", "image": "ipfs://ipfs/" + CID}, "https://ipfs.io/ipfs/" + CID),
    ({"name": "N", "files": [{"src": "ipfs://" + CID, "mediaType": "image/png"}]}, "https://ipfs.io/ipfs/" + CID),
])
async def test_resolver_reads_onchain_metadata(svc, monkeypatch, metadata, expected):
    monkeypatch.setattr(nft_mod, "nftcdn_service", None)
    monkeypatch.setattr(nft_mod, "nmkr_service", None)

    async def fake_headers():
        return {}

    async def fake_fetch(path, headers=None, timeout=None, **kw):
        assert path == f"/assets/{ASSET_CIP68}"
        return FakeResponse(200, {"onchain_metadata": metadata, "metadata": None})

    monkeypatch.setattr(svc, "_get_blockfrost_headers", fake_headers)
    monkeypatch.setattr(nft_mod, "blockfrost_fetch", fake_fetch)

    assert await svc._fetch_nft_image_url(ASSET_CIP68) == expected


# ---------------------------------------------------------------------------
# full refresh keeps already-resolved images
# ---------------------------------------------------------------------------

async def test_full_refresh_carries_previous_images(svc, cache_store, monkeypatch):
    cache_store[(1, nft_mod.NFT_CACHE_KEY)] = {
        "value": {"nfts": [{"asset_id": ASSET_1, "image": "https://ipfs.io/ipfs/" + CID}]},
        "expires_at": (datetime.now() - timedelta(days=1)).isoformat(),  # expired is fine
    }

    async def fake_wallets(user_id=None):
        return [{"id": 7, "blockchain": "cardano", "address": "addr_test_fake", "label": "w"}]

    async def fake_assets(wallet_id):
        return [
            {"asset_id": ASSET_1, "policy_id": POLICY, "asset_name": "NFT01", "quantity": "1"},
            {"asset_id": ASSET_2, "policy_id": POLICY, "asset_name": "NFT02", "quantity": "1"},
        ]

    async def noop(*a, **k):
        return 0

    async def no_price(pid):
        return None

    monkeypatch.setattr(nft_mod, "get_all_wallets", fake_wallets)
    monkeypatch.setattr(nft_mod, "get_wallet_assets", fake_assets)
    monkeypatch.setattr(nft_mod, "get_latest_nft_floor_price", no_price)
    monkeypatch.setattr(svc, "load_floor_prices_from_db", noop)
    monkeypatch.setattr(svc, "_fetch_collection_data", noop)

    nfts = await svc.get_all_nfts(user_id=1, force_refresh=True)
    by_id = {n["asset_id"]: n for n in nfts}
    assert by_id[ASSET_1]["image"].endswith(CID)
    assert "image" not in by_id[ASSET_2]


# ---------------------------------------------------------------------------
# router: GET /nfts returns image_url
# ---------------------------------------------------------------------------

async def test_get_all_nfts_route_returns_image_url(monkeypatch):
    import routers.nfts as router_mod

    async def not_demo(user_id):
        return "someone"

    async def is_demo(username):
        return False

    async def fake_get_all(user_id=None, force_refresh=False):
        return [
            {"asset_id": ASSET_1, "price_ada": None, "image": "https://ipfs.io/ipfs/" + CID},
            {"asset_id": ASSET_2, "price_ada": None, "image_checked": True},
        ]

    async def fake_price(sym):
        return 0.5

    monkeypatch.setattr(router_mod, "get_username_by_user_id", not_demo)
    monkeypatch.setattr(router_mod, "is_demo_user", is_demo)
    monkeypatch.setattr(router_mod.nft_service, "get_all_nfts", fake_get_all)
    monkeypatch.setattr(router_mod.pricing_service, "get_price", fake_price)

    resp = await router_mod.get_all_nfts(user_id=1, force_refresh=False)
    by_id = {n["asset_id"]: n for n in resp["nfts"]}
    assert by_id[ASSET_1]["image_url"].endswith(CID)
    assert by_id[ASSET_2]["image_url"] is None


def test_v2_page_requests_algorand():
    page = os.path.join(BACKEND_DIR, "..", "frontend", "v2", "nfts.html")
    with open(page) as fh:
        src = fh.read()
    assert "'algorand']" in src and 'data-chain="algorand"' in src


@pytest.mark.parametrize("url,ok", [
    ("https://ipfs.io/ipfs/" + CID, True),
    ("data:image/svg+xml;base64,PHN2Zz4=", True),
    ("http://lan-host.example/admin", False),
    ("javascript:alert(1)", False),
    ("data:text/html,<b>x</b>", False),
    (None, False),
])
def test_only_safe_urls_reach_the_browser(svc, monkeypatch, url, ok):
    monkeypatch.setattr(svc, "_schedule_image_backfill", lambda *a: True)
    nfts = [{"asset_id": ASSET_1, "image": url, "image_checked": True}]
    svc.attach_image_urls(nfts, user_id=1)
    assert (nfts[0]["image_url"] is not None) is ok
