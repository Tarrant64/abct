"""Unit tests for services/cardano_token_meta.py (multi-source Cardano token metadata + logo chain).

No network: every source (`fetch_registry`, `fetch_blockfrost`, `fetch_koios`, `fetch_cached_market`,
`fetch_image_bytes`) is monkeypatched. The DB is a temp SQLite file.
"""
import asyncio
import base64
import io
import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import services.cardano_token_meta as ctm  # noqa: E402

POLICY = "ab" * 28
NAME = "4e4654"  # "NFT"
AID = POLICY + NAME


def _png(size=300, color=(200, 30, 30, 255)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGBA", (size, size), color).save(buf, "PNG")
    return buf.getvalue()


def run(c):
    return asyncio.run(c)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(ctm, "DATABASE_PATH", str(tmp_path / "t.db"))
    ctm._reset_for_tests()
    calls = {"registry": 0, "blockfrost": 0, "koios": 0, "market": 0, "image": []}

    async def reg(p, n):
        calls["registry"] += 1
        return {}

    async def bf(p, n):
        calls["blockfrost"] += 1
        return None

    async def ko(p, n):
        calls["koios"] += 1
        return {}

    async def mk(t):
        calls["market"] += 1
        return {}

    async def img(u):
        calls["image"].append(u)
        return None

    monkeypatch.setattr(ctm, "fetch_registry", reg)
    monkeypatch.setattr(ctm, "fetch_blockfrost", bf)
    monkeypatch.setattr(ctm, "fetch_koios", ko)
    monkeypatch.setattr(ctm, "fetch_cached_market", mk)
    monkeypatch.setattr(ctm, "fetch_image_bytes", img)
    return calls, monkeypatch


def test_registry_hit_stops_chain_and_serves_small_png(env):
    calls, mp = env
    b64 = base64.b64encode(_png(400)).decode()

    async def reg(p, n):
        calls["registry"] += 1
        return {"name": "Foo Token", "ticker": "FOO", "decimals": 6, "logo_b64": b64}
    mp.setattr(ctm, "fetch_registry", reg)
    m = run(ctm.resolve(POLICY, NAME))
    assert (m["name"], m["ticker"], m["decimals"], m["has_logo"], m["status"]) == ("Foo Token", "FOO", 6, 1, "found")
    assert calls["blockfrost"] == 0 and calls["koios"] == 0       # complete after source 1
    png, etag = run(ctm.get_logo_blob(AID))
    from PIL import Image
    assert max(Image.open(io.BytesIO(png)).size) == ctm.LOGO_PX and etag


def test_falls_through_to_onchain_image_via_ipfs_gateway(env):
    calls, mp = env

    async def bf(p, n):
        calls["blockfrost"] += 1
        return {"name": "Chain Name", "image_ref": "ipfs://QmSHJHfUJHVtC3VW6o5g6o2spwYDCFrCt6ABEDPSEtBgjT"}

    async def img(u):
        calls["image"].append(u)
        return _png(64) if "pinata" in u else None
    mp.setattr(ctm, "fetch_blockfrost", bf)
    mp.setattr(ctm, "fetch_image_bytes", img)
    m = run(ctm.resolve(POLICY, NAME))
    assert m["has_logo"] == 1 and m["name"] == "Chain Name"
    assert calls["registry"] == 1 and calls["blockfrost"] == 1
    assert calls["image"][0].startswith("https://gateway.pinata.cloud/ipfs/")


def test_koios_used_when_earlier_sources_empty(env):
    calls, mp = env

    async def ko(p, n):
        calls["koios"] += 1
        return {"ticker": "KOI", "decimals": 0}
    mp.setattr(ctm, "fetch_koios", ko)
    m = run(ctm.resolve(POLICY, NAME))
    assert m["ticker"] == "KOI" and m["decimals"] == 0 and not m["has_logo"]


def test_positive_result_is_cached_no_second_network_call(env):
    calls, mp = env

    async def reg(p, n):
        calls["registry"] += 1
        return {"name": "X", "ticker": "XX", "logo_b64": base64.b64encode(_png()).decode()}
    mp.setattr(ctm, "fetch_registry", reg)
    run(ctm.resolve(POLICY, NAME)); run(ctm.resolve(POLICY, NAME))
    assert calls["registry"] == 1


def test_negative_result_cached_shorter_than_positive(env):
    calls, mp = env
    m = run(ctm.resolve(POLICY, "00"))   # every source answers "nothing"
    assert m["status"] == "empty" and not m["has_logo"]
    ttl = m["expires_at"] - m["checked_at"]
    assert abs(ttl - ctm.TTL_EMPTY) < 5 and ctm.TTL_EMPTY < ctm.TTL_FOUND
    run(ctm.resolve(POLICY, "00"))
    assert calls["registry"] == 1


def test_all_sources_erroring_is_short_retry_status(env):
    calls, mp = env

    async def boom(p, n):
        raise RuntimeError("down")
    mp.setattr(ctm, "fetch_registry", boom)
    mp.setattr(ctm, "fetch_koios", boom)
    m = run(ctm.resolve(POLICY, "01"))
    assert m["status"] == "error" and abs((m["expires_at"] - m["checked_at"]) - ctm.TTL_ERROR) < 5


def test_force_bypasses_cache(env):
    calls, mp = env
    run(ctm.resolve(POLICY, NAME)); run(ctm.resolve(POLICY, NAME, force=True))
    assert calls["registry"] == 2


def test_candidate_urls_ssrf_rules():
    assert ctm.candidate_urls("http://169.254.169.254/x.png") == []
    assert ctm.candidate_urls("https://evil.example.com/a.png") == []
    assert ctm.candidate_urls("https://127.0.0.1/a.png") == []
    assert ctm.candidate_urls("https://gateway.pinata.cloud:8443/ipfs/x") == []
    assert ctm.candidate_urls("https://user:pw@ipfs.io/ipfs/x") == []
    assert ctm.candidate_urls("file:///etc/passwd") == []
    assert ctm.candidate_urls("data:image/png;base64,AAAA") == []
    assert ctm.candidate_urls("https://ipfs.io/ipfs/Qm") == ["https://ipfs.io/ipfs/Qm"]
    cid = "Qm" + "a" * 44
    assert ctm.candidate_urls(cid)[0].endswith("/ipfs/" + cid)
    assert ctm.candidate_urls("ar://" + "A" * 43) == ["https://arweave.net/" + "A" * 43]
    assert ctm.candidate_urls("ipfs://ipfs/" + cid)[0].endswith("/ipfs/" + cid)


def test_normalise_rejects_non_images_and_bad_base64():
    assert ctm.normalise_image(b"<svg onload=alert(1)></svg>") is None
    assert ctm.normalise_image(b"not an image") is None
    assert ctm._b64_to_png("%%%not-b64%%%") is None
    assert ctm._b64_to_png("A" * (ctm.MAX_B64_CHARS + 1)) is None
    assert ctm.normalise_image(_png(50)) is not None


def test_enrich_assets_paths_fill_and_negative(env):
    calls, mp = env
    mp.setattr(ctm, "schedule_warm", lambda pairs: len(pairs))
    known = POLICY + "01"
    unknown = POLICY + "02"
    none_ = POLICY + "03"

    async def seed():
        await ctm._save_meta(known, POLICY, "01", {"name": "Known", "ticker": "KNW", "decimals": 6, "has_logo": True, "sources": ["registry"], "coingecko_id": "known"}, "found", 1000)
        await ctm._save_meta(none_, POLICY, "03", {"sources": []}, "empty", 1000)
    run(seed())
    assets = [
        {"asset_id": known, "policy_id": POLICY, "ticker": None, "token_name": "None"},
        {"asset_id": unknown, "policy_id": POLICY},
        {"asset_id": none_, "policy_id": POLICY},
        {"asset_id": "lovelace"},
    ]
    run(ctm.enrich_assets(assets))
    a, b, c, d = assets
    assert a["logo_url"] == f"/api/mobile/token-logo/{POLICY}/01" and a["ticker"] == "KNW" and a["token_name"] == "Known"
    assert a["asset_name_hex"] == "01" and a["policy_id"] == POLICY and a["coingecko_id"] == "known" and a["meta_decimals"] == 6
    assert b["logo_url"] == f"/api/mobile/token-logo/{POLICY}/02"      # unknown: optimistic, endpoint resolves
    assert c["logo_url"] is None                                         # negative cache
    assert "logo_url" not in d
    # fill_ticker=False must not touch ticker
    e = [{"asset_id": known, "policy_id": POLICY, "ticker": None}]
    run(ctm.enrich_assets(e, fill_ticker=False))
    assert e[0]["ticker"] is None and e[0]["meta_ticker"] == "KNW"


def test_logo_endpoint_valid_ids_and_404(env):
    calls, mp = env
    from routers import token_logos
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ei:
        token_logos._ids("zz", "00")
    assert ei.value.status_code == 400
    with pytest.raises(HTTPException):
        token_logos._ids(POLICY, "../../etc")

    class Req:
        headers = {}
    with pytest.raises(HTTPException) as ei:
        run(token_logos.get_token_logo(POLICY, "09", Req(), user_id=1))
    assert ei.value.status_code == 404
    mp.setattr(ctm, "fetch_registry", lambda p, n: asyncio.sleep(0, {"logo_b64": base64.b64encode(_png()).decode()}))
    r = run(token_logos.get_token_logo(POLICY, "0a", Req(), user_id=1))
    assert r.media_type == "image/png" and "max-age" in r.headers["cache-control"] and r.body[:4] == b"\x89PNG"
