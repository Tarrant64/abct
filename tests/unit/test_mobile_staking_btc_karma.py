"""
WQ-0279: BTC Karma positions on the mobile staking endpoint.

GET /api/mobile/defi/staking built only Cardano positions, so the BTC Karma
stake that the web DeFi page shows never appeared in the installed mobile
app. These tests pin:

1. _map_staking_protocol_positions with blockchain='bitcoin' emits the field
   shape the Flutter StakingPosition model parses (blockchain/protocol/
   staked_amount/staked_usd/staked_symbol), with 8-decimal BTC amounts.
2. The Cardano default path is unchanged (blockchain stays 'cardano',
   amounts round at 6).
3. End-to-end through get_mobile_defi_staking: a bitcoin wallet's cached
   btc_karma_staking_* payload yields a position, its USD lands in the
   totals (same iter_staking_token_values valuation the web surfaces use),
   an 'unavailable' status payload yields nothing, and existing Cardano
   positions are untouched.

No network access — the endpoint call is stubbed with a payload shaped
exactly like services.btc_karma.get_btc_karma_staking output.
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import routers.defi as defi_router  # noqa: E402
import routers.mobile as mobile_router  # noqa: E402
from routers.mobile import _map_staking_protocol_positions  # noqa: E402

BTC_PRICE = 115_000.0
ADA_PRICE = 0.60
ALL_PRICES = {
    "ADA": {"usd": ADA_PRICE},
    "BTC": {"usd": BTC_PRICE},
    "INDY": {"usd": 1.10},
}

BTC_AMOUNT = 0.01196600  # the live stake shape (sats / 1e8, 8 decimals)

# Payload exactly like services/btc_karma.get_btc_karma_staking returns
BTC_KARMA_PAYLOAD = {
    "protocols": {
        "BTC Karma": {
            "staked": [{
                "token": "BTC",
                "amount": BTC_AMOUNT,
                "positions": 1,
                "logo_url": "https://img.test/btc.png",
            }],
            "reward_token": "KARMA",
            "rewards_url": "https://staking.btckarma.io",
            "blockchain": "bitcoin",
            "category": "staking",
            "note": "KARMA rewards to Main wallet",
            "total_positions": 1,
            "stake_positions": [{
                "txid": "ab" * 32,
                "vout": 1,
                "amount_btc": BTC_AMOUNT,
                "sats": 1196600,
                "vault_address": "bc1qv015ttest00000000000000000000000000000",
                "confirmed": True,
                "block_time": 1758000000,
                "cardano_wallet": "Main wallet",
            }],
            "source": "bitcoin-chain",
        }
    },
    "address": "bc1qtest0000000000000000000000000000000000",
    "from_cache": True,
}

UNAVAILABLE_PAYLOAD = {
    "protocols": {
        "BTC Karma": {
            "staked": [], "blockchain": "bitcoin", "category": "staking",
            "status": "unavailable",
            "rewards_url": "https://staking.btckarma.io",
        }
    },
    "address": "bc1qtest0000000000000000000000000000000000",
}


@pytest.fixture(autouse=True)
def fake_token_info(monkeypatch):
    async def _fake(symbol):
        return symbol.capitalize(), f"https://img.test/{symbol.lower()}.png"

    monkeypatch.setattr(mobile_router, "_resolve_token_info", _fake)


# ---------------------------------------------------------------------------
# 1+2. mapper: bitcoin chain badge + Cardano default unchanged
# ---------------------------------------------------------------------------

async def test_mapper_bitcoin_shape_matches_flutter_aliases():
    positions, staked_usd, rewards_usd, has_unpriced = (
        await _map_staking_protocol_positions(
            "BTC Karma", BTC_KARMA_PAYLOAD["protocols"]["BTC Karma"],
            ALL_PRICES, ADA_PRICE, blockchain="bitcoin",
        )
    )

    assert len(positions) == 1
    pos = positions[0]
    # Field names the Flutter StakingPosition.fromJson already reads
    assert pos["blockchain"] == "bitcoin"
    assert pos["protocol"] == "BTC Karma"
    assert pos["staked_symbol"] == "BTC"
    assert pos["staked_amount"] == pytest.approx(BTC_AMOUNT)
    assert pos["staked_usd"] == round(BTC_AMOUNT * BTC_PRICE, 2)
    assert pos["active"] is True
    # KARMA rewards are not derivable from public data — nothing to report
    assert rewards_usd == 0
    assert has_unpriced is False
    assert staked_usd == pytest.approx(BTC_AMOUNT * BTC_PRICE)


async def test_mapper_default_blockchain_stays_cardano():
    protocol_data = {"staked": [{"token": "INDY", "amount": 100.123456789}]}
    positions, staked_usd, _, _ = await _map_staking_protocol_positions(
        "Indigo", protocol_data, ALL_PRICES, ADA_PRICE
    )
    assert positions[0]["blockchain"] == "cardano"
    # Cardano tokens keep the old 6-decimal rounding
    assert positions[0]["staked_amount"] == 100.123457


async def test_mapper_bitcoin_keeps_8_decimals():
    protocol_data = {"staked": [{"token": "BTC", "amount": 0.01196604}]}
    positions, _, _, _ = await _map_staking_protocol_positions(
        "BTC Karma", protocol_data, ALL_PRICES, ADA_PRICE, blockchain="bitcoin"
    )
    assert positions[0]["staked_amount"] == pytest.approx(0.01196604)


# ---------------------------------------------------------------------------
# 3. endpoint end-to-end over stubs
# ---------------------------------------------------------------------------

CARDANO_ADDR = "addr1qtestcardanowallet000000000000000000000000000000000"
BTC_ADDR = "bc1qtest0000000000000000000000000000000000"


@pytest.fixture
def endpoint_env(monkeypatch):
    """Endpoint wired to stubs: one bitcoin wallet, no resolvable Cardano
    delegation, no network. The btc-karma call returns the pinned payload."""

    async def fake_wallets(user_id=None):
        return [
            {"id": 1, "address": BTC_ADDR, "blockchain": "bitcoin"},
        ]

    async def fake_get_cache(key, user_id=None):
        return None

    async def fake_get_stale_cache(key, user_id=None):
        return None, None

    async def fake_set_cache(key, value, ttl, user_id=None):
        pass

    async def no_cardano_protocols(address, refresh=False, user_id=None):
        return None

    async def fake_btc_karma(address, refresh=False, user_id=None):
        return dict(BTC_KARMA_PAYLOAD)

    async def stake_address_unavailable(address):
        raise RuntimeError("no stake address")

    from services.pricing import pricing_service

    async def fake_prices():
        return dict(ALL_PRICES)

    monkeypatch.setattr(mobile_router, "get_all_wallets", fake_wallets)
    monkeypatch.setattr(mobile_router, "get_cache", fake_get_cache)
    monkeypatch.setattr(mobile_router, "get_stale_cache", fake_get_stale_cache)
    monkeypatch.setattr(mobile_router, "set_cache", fake_set_cache)
    monkeypatch.setattr(mobile_router.cardano_service, "get_stake_address",
                        stake_address_unavailable)
    monkeypatch.setattr(defi_router, "get_staking_positions",
                        no_cardano_protocols)
    monkeypatch.setattr(defi_router, "get_btc_karma_staking_data",
                        fake_btc_karma)
    monkeypatch.setattr(pricing_service, "get_all_tracked_prices", fake_prices)


async def test_endpoint_includes_btc_karma_position(endpoint_env):
    out = await mobile_router.get_mobile_defi_staking(refresh=False, user_id=1)

    btc = [p for p in out["positions"] if p.get("blockchain") == "bitcoin"]
    assert len(btc) == 1
    assert btc[0]["protocol"] == "BTC Karma"
    assert btc[0]["staked_symbol"] == "BTC"
    assert btc[0]["staked_amount"] == pytest.approx(BTC_AMOUNT)
    # Total agrees with the shared valuation the web DeFi page uses
    assert out["total_staked_usd"] == pytest.approx(
        round(BTC_AMOUNT * BTC_PRICE, 2), rel=1e-3
    )
    assert out["total_rewards_usd"] == 0


async def test_endpoint_unavailable_payload_adds_nothing(monkeypatch, endpoint_env):
    async def unavailable(address, refresh=False, user_id=None):
        return dict(UNAVAILABLE_PAYLOAD)

    monkeypatch.setattr(defi_router, "get_btc_karma_staking_data", unavailable)

    out = await mobile_router.get_mobile_defi_staking(refresh=False, user_id=1)
    assert [p for p in out["positions"] if p.get("blockchain") == "bitcoin"] == []
    assert out["total_staked_usd"] == 0


async def test_endpoint_cardano_positions_unchanged_alongside_btc(monkeypatch, endpoint_env):
    """A cached Cardano protocol position and the BTC Karma position
    coexist; the Cardano row keeps blockchain='cardano'."""

    async def two_wallets(user_id=None):
        return [
            {"id": 1, "address": BTC_ADDR, "blockchain": "bitcoin"},
            {"id": 2, "address": CARDANO_ADDR, "blockchain": "cardano"},
        ]

    monkeypatch.setattr(mobile_router, "get_all_wallets", two_wallets)

    async def cardano_protocols(address, refresh=False, user_id=None):
        return {
            "protocols": {
                "Indigo": {"staked": [{"token": "INDY", "amount": 100.0}]},
            },
            "cached_at": "2026-10-10T00:00:00",
        }

    monkeypatch.setattr(defi_router, "get_staking_positions", cardano_protocols)

    out = await mobile_router.get_mobile_defi_staking(refresh=False, user_id=1)

    cardano = [p for p in out["positions"] if p.get("blockchain") == "cardano"]
    btc = [p for p in out["positions"] if p.get("blockchain") == "bitcoin"]
    assert len(cardano) == 1 and cardano[0]["protocol"] == "Indigo"
    assert len(btc) == 1 and btc[0]["protocol"] == "BTC Karma"
    expected = 100.0 * 1.10 + BTC_AMOUNT * BTC_PRICE
    assert out["total_staked_usd"] == pytest.approx(round(expected, 2), rel=1e-3)
