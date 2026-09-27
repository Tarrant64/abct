"""
Tests for ABCT-BTCKARMA-2026-09-27: BTC Karma Bitcoin staking detection.

The fixtures mirror the exact shape of a real mainnet Esplora response for a
BTC Karma stake: inputs from the staker's P2WPKH address, one P2WSH vault
output and an OP_RETURN of b"CB|" + blake2b-512(cardano bech32 address).
Addresses, txids and amounts are synthetic so no real wallet or stake
is identifiable from this public repo.
No live network calls: services.btc_karma._esplora_get is monkeypatched.
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import services.btc_karma as btc_karma  # noqa: E402

STAKER = "bc1q" + "s" * 38
VAULT = "bc1q" + "v" * 58
CARDANO_ADDR = "addr1q" + "x" * 97
STAKE_TXID = "a" * 64
FUNDING_TXID = "f" * 64
COMMITMENT = btc_karma.cardano_binding_hash(CARDANO_ADDR)
# 0x6a OP_RETURN, 0x4c OP_PUSHDATA1, 0x83 = 131 bytes = len("CB|") + 128 hex chars
OP_RETURN_HEX = "6a4c83" + (b"CB|" + COMMITMENT.encode()).hex()

STAKE_TX = {
    "txid": STAKE_TXID,
    "status": {"confirmed": True, "block_height": 900000, "block_time": 1760000000},
    "vin": [
        {"prevout": {"scriptpubkey_address": STAKER, "value": 1000000}},
        {"prevout": {"scriptpubkey_address": STAKER, "value": 400000}},
        {"prevout": {"scriptpubkey_address": STAKER, "value": 100500}},
    ],
    "vout": [
        {"scriptpubkey_address": VAULT, "scriptpubkey_type": "v0_p2wsh", "value": 1500000},
        {"scriptpubkey": OP_RETURN_HEX, "scriptpubkey_type": "op_return", "value": 0},
    ],
}

# An ordinary incoming payment (exchange withdrawal) - must never count.
FUNDING_TX = {
    "txid": FUNDING_TXID,
    "status": {"confirmed": True, "block_height": 899990, "block_time": 1759990000},
    "vin": [{"prevout": {"scriptpubkey_address": "3" + "e" * 33, "value": 5000000}}],
    "vout": [
        {"scriptpubkey_address": "bc1q" + "w" * 58,
         "scriptpubkey_type": "v0_p2wsh", "value": 2000000},
        {"scriptpubkey_address": STAKER, "scriptpubkey_type": "v0_p2wpkh", "value": 400000},
    ],
}


def fake_esplora(spent=False, fail=False):
    calls = []

    async def _get(path):
        calls.append(path)
        if fail:
            raise btc_karma.BtcKarmaUnavailable("mempool.space HTTP 503")
        if path == f"/address/{STAKER}/txs":
            return [STAKE_TX, FUNDING_TX]
        if path == f"/tx/{STAKE_TXID}/outspend/0":
            return {"spent": spent}
        raise AssertionError(f"unexpected path {path}")

    return _get, calls


def test_binding_hash_is_blake2b_512_of_bech32_text():
    """The OP_RETURN payload is blake2b-512 over the UTF-8 bech32 address text
    (verified against a live mainnet stake during discovery)."""
    import hashlib
    h = btc_karma.cardano_binding_hash(CARDANO_ADDR)
    assert len(h) == 128
    assert h == hashlib.blake2b(CARDANO_ADDR.encode(), digest_size=64).hexdigest()
    assert h != btc_karma.cardano_binding_hash("addr1q" + "y" * 97)


def test_parse_op_return_pushdata_forms():
    assert btc_karma.parse_op_return(OP_RETURN_HEX).startswith(b"CB|")
    assert btc_karma.parse_op_return("6a03" + b"abc".hex()) == b"abc"
    assert btc_karma.parse_op_return("6a4d0300" + b"xyz".hex()) == b"xyz"
    assert btc_karma.parse_op_return("0014" + "00" * 20) is None  # not OP_RETURN
    assert btc_karma.parse_op_return("6a4c05ab") is None  # truncated push
    assert btc_karma.parse_op_return("zz") is None


def test_find_stake_outputs_ignores_plain_payments():
    stakes = btc_karma.find_stake_outputs([STAKE_TX, FUNDING_TX], STAKER)
    assert len(stakes) == 1
    s = stakes[0]
    assert (s["txid"], s["vout"], s["sats"], s["vault_address"]) == (STAKE_TXID, 0, 1500000, VAULT)
    assert s["cardano_commitment"] == btc_karma.cardano_binding_hash(CARDANO_ADDR)


def test_find_stake_outputs_requires_spend_from_address():
    """A CB| tx funded by someone else is not this address's stake."""
    assert btc_karma.find_stake_outputs([STAKE_TX], "bc1q" + "z" * 38) == []


@pytest.mark.parametrize("address,ok", [
    (STAKER, True),
    (VAULT, True),
    ("1" + "A" * 33, True),
    ("3" + "e" * 33, True),
    ("tb1q" + "s" * 38, False),  # testnet
    ("bc1q../../tx/abc", False),
    ("BC1Q" + "S" * 38, False),
    ("", False),
    ("xpub6BosfCnifzxcFwrSzQiqu2DBVTshkCXacvNsWGYJVVhhawA7d4R5WSWGFNbi8Aw6ZRc1brxMyWMzG3DSSSSoekkudhUd9yLb6qx39T9nMdj", False),
])
def test_address_validation(address, ok):
    assert btc_karma.is_valid_btc_address(address) is ok


async def test_active_stake_reported_with_cardano_binding(monkeypatch):
    fake, calls = fake_esplora(spent=False)
    monkeypatch.setattr(btc_karma, "_esplora_get", fake)

    result = await btc_karma.get_btc_karma_staking(
        STAKER, [{"address": CARDANO_ADDR, "label": "Main ADA"}, {"address": "addr1other", "label": "x"}]
    )

    proto = result["protocols"]["BTC Karma"]
    assert proto["blockchain"] == "bitcoin"
    assert proto["category"] == "staking"
    assert proto["staked"][0]["token"] == "BTC"
    assert proto["staked"][0]["amount"] == pytest.approx(0.01500000)
    assert proto["staked"][0]["positions"] == 1
    assert proto["note"] == "KARMA rewards to Main ADA"
    assert proto["stake_positions"][0]["cardano_wallet"] == "Main ADA"
    assert calls == [f"/address/{STAKER}/txs", f"/tx/{STAKE_TXID}/outspend/0"]


async def test_unbound_cardano_wallet_is_flagged(monkeypatch):
    fake, _ = fake_esplora(spent=False)
    monkeypatch.setattr(btc_karma, "_esplora_get", fake)

    result = await btc_karma.get_btc_karma_staking(STAKER, [])

    assert result["protocols"]["BTC Karma"]["note"] == "KARMA rewards to an untracked Cardano wallet"


async def test_unstaked_vault_drops_out(monkeypatch):
    """Once the vault output is spent (unstaked) there is no position."""
    fake, _ = fake_esplora(spent=True)
    monkeypatch.setattr(btc_karma, "_esplora_get", fake)

    assert await btc_karma.get_btc_karma_staking(STAKER, []) is None


async def test_api_failure_raises_unavailable(monkeypatch):
    fake, _ = fake_esplora(fail=True)
    monkeypatch.setattr(btc_karma, "_esplora_get", fake)

    with pytest.raises(btc_karma.BtcKarmaUnavailable):
        await btc_karma.get_btc_karma_staking(STAKER, [])


async def test_invalid_address_never_reaches_the_api(monkeypatch):
    fake, calls = fake_esplora()
    monkeypatch.setattr(btc_karma, "_esplora_get", fake)

    with pytest.raises(ValueError):
        await btc_karma.get_btc_karma_staking("bc1q/../../evil", [])
    assert calls == []


class _Resp:
    def __init__(self, status_code, data=None):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data


class _Client:
    def __init__(self, responses):
        self.responses = responses
        self.urls = []

    async def get(self, url, timeout=None):
        self.urls.append(url)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


async def test_esplora_falls_back_to_blockstream(monkeypatch):
    client = _Client([_Resp(503), _Resp(200, {"spent": False})])
    monkeypatch.setattr(btc_karma, "get_client", lambda *a, **k: client)

    data = await btc_karma._esplora_get("/tx/abc/outspend/0")

    assert data == {"spent": False}
    assert client.urls[0].startswith(btc_karma.MEMPOOL_BASE_URL)
    assert client.urls[1].startswith(btc_karma.BLOCKSTREAM_BASE_URL)


async def test_esplora_all_providers_down(monkeypatch):
    client = _Client([TimeoutError("t1"), _Resp(500)])
    monkeypatch.setattr(btc_karma, "get_client", lambda *a, **k: client)

    with pytest.raises(btc_karma.BtcKarmaUnavailable):
        await btc_karma._esplora_get("/address/x/txs")


# ---------------------------------------------------------------------------
# /defi/btc-karma/{address} endpoint: graceful failure, never breaks the page
# ---------------------------------------------------------------------------

@pytest.fixture
def router(monkeypatch):
    import routers.defi as defi_router

    store = {}

    async def fake_get_cache(key, user_id=None):
        return None

    async def fake_set_cache(key, value, ttl_seconds=300, user_id=None):
        store[key] = value

    async def fake_stale(key, user_id=None):
        return store.get(("stale", key)), None

    async def fake_wallets(user_id=None):
        return [{"address": CARDANO_ADDR, "label": "Main ADA", "blockchain": "cardano"},
                {"address": STAKER, "label": "BTC", "blockchain": "bitcoin"}]

    monkeypatch.setattr(defi_router, "get_cache", fake_get_cache)
    monkeypatch.setattr(defi_router, "set_cache", fake_set_cache)
    monkeypatch.setattr(defi_router, "get_stale_cache", fake_stale)
    monkeypatch.setattr(defi_router, "get_all_wallets", fake_wallets)
    return defi_router, store


async def test_endpoint_reports_stake_and_caches(router, monkeypatch):
    defi_router, store = router
    fake, _ = fake_esplora(spent=False)
    monkeypatch.setattr(btc_karma, "_esplora_get", fake)

    result = await defi_router.get_btc_karma_staking_data(STAKER, refresh=True, user_id=1)

    assert result["protocols"]["BTC Karma"]["note"] == "KARMA rewards to Main ADA"
    assert f"btc_karma_staking_{STAKER}" in store


async def test_endpoint_unavailable_without_stale_cache(router, monkeypatch):
    defi_router, store = router
    fake, _ = fake_esplora(fail=True)
    monkeypatch.setattr(btc_karma, "_esplora_get", fake)

    result = await defi_router.get_btc_karma_staking_data(STAKER, refresh=True, user_id=1)

    proto = result["protocols"]["BTC Karma"]
    assert proto["status"] == "unavailable" and proto["staked"] == []
    assert store == {}  # a failure is never cached


async def test_endpoint_serves_stale_on_failure(router, monkeypatch):
    defi_router, store = router
    store[("stale", f"btc_karma_staking_{STAKER}")] = {"protocols": {"BTC Karma": {"staked": [1]}}}
    fake, _ = fake_esplora(fail=True)
    monkeypatch.setattr(btc_karma, "_esplora_get", fake)

    result = await defi_router.get_btc_karma_staking_data(STAKER, refresh=True, user_id=1)

    assert result["stale_fallback"] is True and result["from_cache"] is True


async def test_endpoint_rejects_malformed_address(router):
    from fastapi import HTTPException
    defi_router, _ = router

    with pytest.raises(HTTPException) as exc:
        await defi_router.get_btc_karma_staking_data("not-an-address", user_id=1)
    assert exc.value.status_code == 400
