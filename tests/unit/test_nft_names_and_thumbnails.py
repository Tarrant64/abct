"""
Unit tests: NFT names ("Unknown" fix) and on-demand thumbnails.

- Cardano NFTs have no ``name`` key; the wall used to emit "Unknown" for every one.
- The thumbnail route used to return the multi-MB original when thumbnail_data
  was NULL; it now generates (and stores) a thumbnail, or refuses.

No network. A throwaway sqlite file stands in for the image DB. Synthetic ids.
"""
import asyncio
import io
import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from services import nft_names  # noqa: E402

POLICY = "cd" * 28


# ---------------------------------------------------------------- name helpers
def test_cip25_metadata_name_wins():
    nft = {'asset_id': POLICY + "4e46543031", 'name': '  Space Bud #42 ', 'asset_name': 'NFT01'}
    assert nft_names.resolve_cardano_name(nft) == 'Space Bud #42'


def test_metadata_name_as_chunk_list():
    assert nft_names.name_from_metadata({'name': ['Long ', 'Name']}) == 'Long Name'


def test_name_from_metadata_strips_control_chars_and_bounds_length():
    assert nft_names.name_from_metadata({'name': 'A\x00B\x1b[0m'}) == 'AB[0m'
    assert len(nft_names.name_from_metadata({'name': 'x' * 5000})) == nft_names.MAX_NAME_LEN


def test_hex_asset_name_decoded():
    nft = {'asset_id': POLICY + "4e46543031"}          # "NFT01"
    assert nft_names.resolve_cardano_name(nft) == 'NFT01'
    nft2 = {'asset_name_hex': "4e46543032", 'asset_id': POLICY + "4e46543032"}
    assert nft_names.resolve_cardano_name(nft2) == 'NFT02'


def test_cip68_label_prefix_dropped():
    assert nft_names.decode_asset_name("000de140" + "4e4654") == 'NFT'


def test_non_printable_hex_falls_back_to_raw_asset_name_then_none():
    nft = {'asset_id': POLICY + "00ff01", 'asset_name_hex': "00ff01", 'asset_name': 'RawName'}
    assert nft_names.resolve_cardano_name(nft) == 'RawName'
    assert nft_names.resolve_cardano_name({'asset_id': POLICY + "00ff01", 'asset_name_hex': "00ff01"}) is None


def test_placeholders_are_not_names():
    assert nft_names.clean_name('Unknown') is None
    assert nft_names.clean_name('') is None
    assert nft_names.clean_name(None) is None
    assert nft_names.clean_collection({'collection': {'name': 'Unknown Collection'}}) is None
    assert nft_names.clean_collection({'collection': {'name': 'Cool Club'}}) == 'Cool Club'


def test_blockfrost_response_records_name_without_extra_call(monkeypatch):
    import services.nft as nft_mod

    class Resp:
        status_code = 200
        def json(self):
            return {'onchain_metadata': {'name': 'Bud #7', 'image': 'ipfs://Qm' + 'x' * 44}}

    async def fake_bf(*a, **k):
        return Resp()

    async def no_hdr():
        return {}

    monkeypatch.setattr(nft_mod, 'nftcdn_service', None)
    monkeypatch.setattr(nft_mod, 'nmkr_service', None)
    monkeypatch.setattr(nft_mod, 'blockfrost_fetch', fake_bf)
    svc = nft_mod.NFTService()
    monkeypatch.setattr(svc, '_get_blockfrost_headers', no_hdr)
    aid = POLICY + "4e46543031"
    url = asyncio.run(svc._fetch_nft_image_url(aid))
    assert url and svc._resolved_names[aid] == 'Bud #7'


# ------------------------------------------------------------ image DB fixtures
def _png(size, color=(200, 30, 30)):
    from PIL import Image
    buf = io.BytesIO()
    Image.effect_noise(size, 80).convert('RGB').save(buf, format='PNG')  # noisy -> large file
    return buf.getvalue()


@pytest.fixture
def image_db(tmp_path, monkeypatch):
    import config
    import nft_image_database as db
    path = tmp_path / "nft_images.db"
    monkeypatch.setattr(db, 'NFT_IMAGE_DB_PATH', path)
    monkeypatch.setattr(config, 'NFT_IMAGE_DB_PATH', path)
    asyncio.run(db.init_nft_image_db())
    return db


@pytest.fixture
def svc(image_db):
    import services.nft_image_service as m
    s = m.NFTImageService()
    s._initialized = True
    return s


def _store(db, asset, data, fmt, chain='cardano'):
    asyncio.run(db.save_nft_image(asset_id=asset, blockchain=chain, image_url='https://x/y',
                                  image_data=data, image_format=fmt, fetch_status='fetched'))


# -------------------------------------------------------------- thumbnail route
def test_thumbnail_generated_on_demand_stored_and_small(image_db, svc, monkeypatch):
    import routers.nfts as r
    monkeypatch.setattr(r, 'nft_image_service', svc)
    big = _png((2400, 2400))
    assert len(big) > 1_000_000
    _store(image_db, 'a1', big, 'png')

    resp = asyncio.run(r.get_cached_thumbnail('cardano', 'a1'))
    assert resp.media_type == 'image/jpeg'
    assert 0 < len(resp.body) < 300_000
    from PIL import Image
    assert max(Image.open(io.BytesIO(resp.body)).size) <= 480
    # stored once: now served straight from thumbnail_data
    stored, _ = asyncio.run(image_db.get_nft_thumbnail_data('a1', 'cardano'))
    assert stored == resp.body


def test_thumbnail_never_returns_big_original(image_db, svc, monkeypatch):
    from fastapi import HTTPException
    import routers.nfts as r
    monkeypatch.setattr(r, 'nft_image_service', svc)
    big_svg = b'<svg xmlns="http://www.w3.org/2000/svg">' + b'<!--' + b'x' * 2_000_000 + b'--></svg>'
    _store(image_db, 'svgbig', big_svg, 'svg')
    with pytest.raises(HTTPException) as e:
        asyncio.run(r.get_cached_thumbnail('cardano', 'svgbig'))
    assert e.value.status_code == 415


def test_small_svg_served_as_is_and_missing_is_404(image_db, svc, monkeypatch):
    from fastapi import HTTPException
    import routers.nfts as r
    monkeypatch.setattr(r, 'nft_image_service', svc)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>'
    _store(image_db, 'svgsmall', svg, 'svg')
    resp = asyncio.run(r.get_cached_thumbnail('cardano', 'svgsmall'))
    assert resp.media_type == 'image/svg+xml' and resp.body == svg
    with pytest.raises(HTTPException) as e:
        asyncio.run(r.get_cached_thumbnail('cardano', 'nope'))
    assert e.value.status_code == 404


def test_pillow_missing_refuses_instead_of_serving_original(image_db, svc, monkeypatch):
    from fastapi import HTTPException
    import routers.nfts as r
    import services.nft_image_service as m
    monkeypatch.setattr(r, 'nft_image_service', svc)
    monkeypatch.setattr(m, 'PILLOW_AVAILABLE', False)
    _store(image_db, 'nopil', _png((1500, 1500)), 'png')
    with pytest.raises(HTTPException) as e:
        asyncio.run(r.get_cached_thumbnail('cardano', 'nopil'))
    assert e.value.status_code == 415


def test_pixel_bomb_rejected(image_db, svc, monkeypatch):
    import services.nft_image_service as m
    monkeypatch.setattr(m, 'MAX_SOURCE_PIXELS', 1000)
    assert svc._resize_checked(_png((200, 200)), 'png', 480, 'JPEG') is None


def test_mobile_route_generates_webp_and_stays_small(image_db, svc, monkeypatch):
    import routers.nfts as r
    monkeypatch.setattr(r, 'nft_image_service', svc)
    _store(image_db, 'm1', _png((2000, 2000)), 'png')
    resp = asyncio.run(r.get_cached_mobile_image('cardano', 'm1'))
    assert resp.media_type == 'image/webp' and len(resp.body) < 300_000


# ------------------------------------------------------------------ wall builder
def test_wall_never_emits_unknown(image_db, monkeypatch):
    import database
    import config
    import routers.nfts as r

    named = POLICY + "4e46543031"                 # decodes to NFT01
    meta = POLICY + "4e46543032"
    anon = POLICY + "00ff01"                      # not text
    nfts = [
        {'asset_id': named, 'collection': {'name': ''}, 'price_ada': None},
        {'asset_id': meta, 'name': 'Bud #2', 'collection': {'name': 'Buds'}, 'price_ada': 5},
        {'asset_id': anon, 'asset_name_hex': '00ff01', 'collection': {}, 'price_ada': None},
    ]
    for n in nfts:
        _store(image_db, n['asset_id'], b'\x89PNG', 'png')

    async def fake_get_all(user_id=None, force_refresh=False):
        return nfts

    async def none(*a, **k):
        return None

    async def price(sym):
        return 1.0

    async def false(*a, **k):
        return False

    async def no_wallets(*a, **k):
        return []

    monkeypatch.setattr(r.nft_service, 'get_all_nfts', fake_get_all)
    monkeypatch.setattr(r.nft_service, 'schedule_name_backfill', lambda *a, **k: False)
    monkeypatch.setattr(r.pricing_service, 'get_price', price)
    monkeypatch.setattr(r, 'get_username_by_user_id', none)
    monkeypatch.setattr(r, 'get_all_wallets', no_wallets)
    monkeypatch.setattr(r.solana_nft_service, 'is_configured', false)
    monkeypatch.setattr(r.polygon_service, 'is_configured', false)
    monkeypatch.setattr(r.base_service, 'is_configured', false)
    monkeypatch.setattr(r.ethereum_nft_service, 'is_configured', lambda: False)
    monkeypatch.setattr(database, 'get_cache', none)
    monkeypatch.setattr(database, 'set_cache', none)

    res = asyncio.run(r.get_nfts_with_images(user_id=1, blockchain='cardano', group_by_collection=False,
                                     include_thumbnails=None))
    by_id = {n['asset_id']: n for n in res['nfts']}
    assert by_id[named]['name'] == 'NFT01'
    assert by_id[meta]['name'] == 'Bud #2'
    assert by_id[anon]['name'] is None
    assert by_id[named]['collection'] is None and by_id[meta]['collection'] == 'Buds'
    blob = repr(res)
    assert 'Unknown' not in blob
