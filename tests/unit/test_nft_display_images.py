"""
Unit tests for ABCT-NFT-DIAG2-2026-09-28 ("I only see Ethereum" on the NFT page).

After #12 every Cardano NFT had an image URL on the public ipfs.io gateway,
which now answers hot-linked images with a Cloudflare challenge (403/429).
Every Cardano (and the Algorand) image failed, and Gallery Mode hides tiles
whose image fails, so only Ethereum NFTs were left. In addition:
- the All Chains grid rendered at most 100 cards, so chains whose NFTs sort
  below the 100th card by value (Algorand, Solana) never appeared there;
- a Solana wallet added after the last NFT fetch stayed invisible for up to
  24 h (in-memory cache) or 30 days (persistent cache);
- collection objects rendered as "[object Object]".

No network, no real keys or addresses: HTTP, DB and cache are mocked, and the
wallet addresses / CIDs below are synthetic.
"""

import os
import sys
from datetime import datetime, timedelta

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import services.nft_display_images as disp  # noqa: E402
import services.solana_nft as sol_mod  # noqa: E402

CID0 = "Qm" + "a" * 44                      # synthetic CIDv0
CID1 = "bafybei" + "a" * 52                 # synthetic CIDv1 (base32)
GATEWAYS = ["https://gw-one.example/ipfs/", "https://gw-two.example/ipfs/"]
PAGE = os.path.join(BACKEND_DIR, "..", "frontend", "v2", "nfts.html")


# ---------------------------------------------------------------------------
# ipfs_path / display_image_candidates
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("ipfs://" + CID0, CID0),
    ("ipfs://ipfs/" + CID0, CID0),
    (CID0, CID0),
    (CID1, CID1),
    ("https://ipfs.io/ipfs/" + CID0, CID0),
    ("http://some-gateway.example/ipfs/" + CID1 + "/img.png", CID1 + "/img.png"),
    ("ipfs://" + CID1 + "/Red – Common.mp4", CID1 + "/Red%20%E2%80%93%20Common.mp4"),
    ("https://ipfs.io/ipfs/" + CID0 + "/a.png?x=1", CID0 + "/a.png"),
    ("ipfs://" + CID0 + "/../secret", None),
    ("https://cdn.example/art.png", None),
    ("ipfs://not-a-cid", None),
    ("banana-bread-is-not-a-cid-at-all", None),
    (None, None),
    ("", None),
])
def test_ipfs_path(url, expected):
    assert disp.ipfs_path(url) == expected


def test_ipfs_content_is_offered_on_every_gateway_in_order():
    got = disp.display_image_candidates("https://ipfs.io/ipfs/" + CID0, gateways=GATEWAYS)
    assert got == [g + CID0 for g in GATEWAYS]


def test_non_https_gateways_are_ignored():
    got = disp.display_image_candidates("ipfs://" + CID0, gateways=["http://lan-gw.example/ipfs/"] + GATEWAYS)
    assert got == [g + CID0 for g in GATEWAYS]


@pytest.mark.parametrize("url,expected", [
    ("https://cdn.example/art.png", ["https://cdn.example/art.png"]),
    ("data:image/svg+xml;base64,PHN2Zz4=", ["data:image/svg+xml;base64,PHN2Zz4="]),
    ("http://lan-host.example/admin", []),
    ("javascript:alert(1)", []),
    ("data:text/html,<b>x</b>", []),
    (None, []),
])
def test_non_ipfs_urls_pass_only_if_browser_safe(url, expected):
    assert disp.display_image_candidates(url, gateways=GATEWAYS) == expected


def test_attach_display_images_sets_url_and_fallbacks(monkeypatch):
    monkeypatch.setattr(disp, "NFT_DISPLAY_IPFS_GATEWAYS", GATEWAYS)
    nft = disp.attach_display_images({}, "ipfs://" + CID0)
    assert nft["image_url"] == GATEWAYS[0] + CID0
    assert nft["image_fallbacks"] == [GATEWAYS[1] + CID0]
    empty = disp.attach_display_images({}, "http://lan-host.example/x.png")
    assert empty["image_url"] is None and empty["image_fallbacks"] == []


def test_default_gateways_are_https_and_not_ipfs_io_first():
    import config
    assert config.NFT_DISPLAY_IPFS_GATEWAYS, "at least one display gateway"
    assert all(g.startswith("https://") and g.endswith("/ipfs/") for g in config.NFT_DISPLAY_IPFS_GATEWAYS)
    assert not config.NFT_DISPLAY_IPFS_GATEWAYS[0].startswith("https://ipfs.io/")


# ---------------------------------------------------------------------------
# Cardano /nfts route + Algorand route carry fallbacks
# ---------------------------------------------------------------------------

async def _not_demo_setup(monkeypatch, router_mod):
    async def username(user_id):
        return "someone"

    async def is_demo(username):
        return False

    monkeypatch.setattr(router_mod, "get_username_by_user_id", username)
    monkeypatch.setattr(router_mod, "is_demo_user", is_demo)


async def test_cardano_route_returns_gateway_fallbacks(monkeypatch):
    import routers.nfts as router_mod
    await _not_demo_setup(monkeypatch, router_mod)
    monkeypatch.setattr(disp, "NFT_DISPLAY_IPFS_GATEWAYS", GATEWAYS)

    async def fake_get_all(user_id=None, force_refresh=False):
        return [{"asset_id": "p" * 56 + "01", "price_ada": None, "image": "https://ipfs.io/ipfs/" + CID0}]

    async def fake_price(sym):
        return 0.5

    monkeypatch.setattr(router_mod.nft_service, "get_all_nfts", fake_get_all)
    monkeypatch.setattr(router_mod.nft_service, "_schedule_image_backfill", lambda *a: True)
    monkeypatch.setattr(router_mod.pricing_service, "get_price", fake_price)

    resp = await router_mod.get_all_nfts(user_id=1, force_refresh=False)
    nft = resp["nfts"][0]
    assert nft["image_url"] == GATEWAYS[0] + CID0
    assert nft["image_fallbacks"] == [GATEWAYS[1] + CID0]


async def test_algorand_route_returns_gateway_fallbacks(monkeypatch):
    import routers.nfts as router_mod
    await _not_demo_setup(monkeypatch, router_mod)
    monkeypatch.setattr(disp, "NFT_DISPLAY_IPFS_GATEWAYS", GATEWAYS)

    async def fake_wallets(user_id=None):
        return [{"address": "ALGO-TEST-WALLET", "blockchain": "algorand"}]

    async def fake_nfts(address):
        return [{"asset_id": 1, "name": "Test", "image_url": "https://ipfs.io/ipfs/" + CID0}]

    monkeypatch.setattr(router_mod, "get_all_wallets", fake_wallets)
    monkeypatch.setattr(router_mod.algorand_nft_service, "get_nfts_for_address", fake_nfts)

    resp = await router_mod.get_algorand_nfts(user_id=1, force_refresh=False)
    nft = resp["nfts"][0]
    assert nft["image_url"] == GATEWAYS[0] + CID0
    assert nft["image_fallbacks"] == [GATEWAYS[1] + CID0]


# ---------------------------------------------------------------------------
# Solana: a wallet added after the last fetch is picked up
# ---------------------------------------------------------------------------

WALLET_A = "SolTestWalletA" + "1" * 20
WALLET_B = "SolTestWalletB" + "2" * 20


@pytest.fixture
def sol_env(monkeypatch):
    env = {"wallets": [WALLET_A], "cache": None, "fetches": [], "saved": []}

    async def fake_wallets(user_id=None):
        return [{"address": a, "blockchain": "solana"} for a in env["wallets"]]

    async def fake_get_cache(key, user_id=None):
        return env["cache"]

    async def fake_set_cache(key, value, ttl_seconds=300, user_id=None):
        env["saved"].append(value)

    svc = sol_mod.SolanaNFTService()

    async def configured():
        return True

    async def fake_assets(address, page=1):
        env["fetches"].append(address)
        return {"items": [{"id": "asset-" + address[-4:]}], "total": 1}

    def fake_parse(asset, address):
        return {"asset_id": asset["id"], "name": "Hotspot", "image_url": "https://img.example/h.png",
                "collection": {"id": "helium", "name": "Helium", "floor_price_sol": 0}}

    monkeypatch.setattr(sol_mod, "get_all_wallets", fake_wallets)
    monkeypatch.setattr(sol_mod, "get_cache", fake_get_cache)
    monkeypatch.setattr(sol_mod, "set_cache", fake_set_cache)
    monkeypatch.setattr(svc, "is_configured", configured)
    monkeypatch.setattr(svc, "get_assets_by_owner", fake_assets)
    monkeypatch.setattr(svc, "_parse_nft", fake_parse)
    env["svc"] = svc
    return env


async def test_unchanged_wallets_use_the_cache(sol_env):
    svc = sol_env["svc"]
    first = await svc.get_all_solana_nfts(user_id=1)
    assert len(first) == 1 and sol_env["fetches"] == [WALLET_A]
    again = await svc.get_all_solana_nfts(user_id=1)
    assert len(again) == 1 and sol_env["fetches"] == [WALLET_A]  # no second fetch


async def test_added_wallet_invalidates_fresh_in_memory_cache(sol_env):
    svc = sol_env["svc"]
    await svc.get_all_solana_nfts(user_id=1)
    sol_env["wallets"].append(WALLET_B)
    nfts = await svc.get_all_solana_nfts(user_id=1)
    assert len(nfts) == 2
    assert sol_env["fetches"] == [WALLET_A, WALLET_A, WALLET_B]


async def test_persisted_cache_for_other_wallet_set_is_refetched(sol_env):
    svc = sol_env["svc"]
    # A fresh-looking persisted snapshot from before the wallet was added
    # (legacy rows carry no fingerprint at all)
    sol_env["cache"] = {"nfts": [], "collections": {},
                        "last_refresh": (datetime.now() - timedelta(minutes=5)).isoformat()}
    nfts = await svc.get_all_solana_nfts(user_id=1)
    assert len(nfts) == 1 and sol_env["fetches"] == [WALLET_A]


async def test_persisted_cache_for_same_wallet_set_is_used(sol_env):
    svc = sol_env["svc"]
    sol_env["cache"] = {"nfts": [{"asset_id": "cached", "collection": {"name": "x"}}], "collections": {},
                        "last_refresh": datetime.now().isoformat(),
                        "wallet_fingerprint": sol_mod.wallet_fingerprint([WALLET_A])}
    nfts = await svc.get_all_solana_nfts(user_id=1)
    assert [n["asset_id"] for n in nfts] == ["cached"] and sol_env["fetches"] == []


async def test_saved_cache_stores_a_hash_not_addresses(sol_env):
    svc = sol_env["svc"]
    await svc.get_all_solana_nfts(user_id=1)
    saved = sol_env["saved"][-1]
    assert saved["wallet_fingerprint"] == sol_mod.wallet_fingerprint([WALLET_A])
    assert WALLET_A not in saved["wallet_fingerprint"]
    assert len(saved["wallet_fingerprint"]) == 64


def test_fingerprint_is_order_independent():
    assert sol_mod.wallet_fingerprint([WALLET_A, WALLET_B]) == sol_mod.wallet_fingerprint([WALLET_B, WALLET_A])
    assert sol_mod.wallet_fingerprint([WALLET_A]) != sol_mod.wallet_fingerprint([WALLET_A, WALLET_B])


# ---------------------------------------------------------------------------
# v2 NFT page (static checks; the render path was also exercised in a real
# browser against production data for the diagnosis report)
# ---------------------------------------------------------------------------

def _page():
    with open(PAGE) as fh:
        return fh.read()


def test_page_tries_fallback_gateways_before_giving_up():
    src = _page()
    assert "function nftImgFallback(" in src and "image_fallbacks" in src
    assert 'onerror="nftImgFallback(this)"' in src
    # the old one-shot handlers that hid the tile/image on the first error are gone
    assert "onerror=\"this.parentElement.style.display" not in src


def test_page_never_uses_non_https_image_urls():
    src = _page()
    assert "function nftSafeImageUrl(" in src
    assert "nft.image_url || nft.image || nft.thumbnail" not in src


def test_all_chains_grid_is_not_capped_at_100():
    src = _page()
    assert "items.slice(0, 100)" not in src
    assert "nftShowMoreBtn" in src


def test_collection_objects_render_by_name():
    src = _page()
    assert "function nftCollectionName(" in src
    assert "nft._collection || nft.collection || nft.policy_id" not in src
