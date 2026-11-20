"""
Server-fixes item 2 (2026-11-20): /api/mobile/defi/staking positions carry
wallet attribution -- wallet_id / wallet_label / wallet_address plus a
`wallets: [{wallet_id, label, value_usd}]` breakdown.

Design choice: positions are already produced per wallet (never merged across
wallets), so the least disruptive option is to tag every row rather than
split or re-group anything. Totals are unchanged.
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

from tests.unit.test_mobile_staking_btc_karma import (  # noqa: E402,F401
    ADA_PRICE, BTC_ADDR, BTC_AMOUNT, BTC_PRICE, CARDANO_ADDR, endpoint_env,
)

CARDANO_ADDR_2 = "addr1qtestcardanowallet2000000000000000000000000000000000"


def _wallets():
    return [
        {"id": 1, "address": BTC_ADDR, "blockchain": "bitcoin", "label": "Cold BTC"},
        {"id": 2, "address": CARDANO_ADDR, "blockchain": "cardano", "label": "Main"},
        {"id": 3, "address": CARDANO_ADDR_2, "blockchain": "cardano", "label": None},
    ]


async def test_protocol_rows_tagged_per_wallet_totals_unchanged(monkeypatch, endpoint_env):  # noqa: F811
    async def wallets(user_id=None):
        return _wallets()
    monkeypatch.setattr(mobile_router, "get_all_wallets", wallets)

    async def cardano_protocols(address, refresh=False, user_id=None):
        amt = 100.0 if address == CARDANO_ADDR else 50.0
        return {"protocols": {"Indigo": {"staked": [{"token": "INDY", "amount": amt}]}}}
    monkeypatch.setattr(defi_router, "get_staking_positions", cardano_protocols)

    out = await mobile_router.get_mobile_defi_staking(refresh=False, user_id=1)
    indy = {p["wallet_id"]: p for p in out["positions"] if p.get("protocol") == "Indigo"}
    assert set(indy) == {2, 3}
    assert indy[2]["wallet_label"] == "Main"
    assert indy[2]["wallet_address"] == CARDANO_ADDR
    assert indy[3]["wallet_label"] is None
    assert indy[2]["wallets"] == [{"wallet_id": 2, "label": "Main",
                                   "value_usd": indy[2]["staked_usd"]}]
    btc = next(p for p in out["positions"] if p["blockchain"] == "bitcoin")
    assert btc["wallet_id"] == 1 and btc["wallet_address"] == BTC_ADDR

    expected = (100.0 + 50.0) * 1.10 + BTC_AMOUNT * BTC_PRICE
    assert out["total_staked_usd"] == pytest.approx(round(expected, 2), rel=1e-3)


async def test_native_delegation_lists_all_wallets_sharing_stake_key(monkeypatch, endpoint_env):  # noqa: F811
    async def wallets(user_id=None):
        return _wallets()[1:]
    monkeypatch.setattr(mobile_router, "get_all_wallets", wallets)

    async def stake(address):
        return "stake1utestsharedkey"
    async def info(stake_address):
        return {"controlled_ada": 1000.0, "withdrawable_ada": 5.0,
                "pool_id": "pool1x", "pool_name": "Pool", "pool_ticker": "PL"}
    monkeypatch.setattr(mobile_router.cardano_service, "get_stake_address", stake)
    monkeypatch.setattr(mobile_router.cardano_service, "get_stake_account_info", info)
    monkeypatch.setattr(mobile_router, "_derive_stake_key_local", lambda a: None, raising=False)
    import services.cardano as svc
    monkeypatch.setattr(svc, "_derive_stake_key_local", lambda a: None)

    async def none_protocols(address, refresh=False, user_id=None):
        return None
    monkeypatch.setattr(defi_router, "get_staking_positions", none_protocols)

    out = await mobile_router.get_mobile_defi_staking(refresh=False, user_id=1)
    native = [p for p in out["positions"] if p.get("stake_key")]
    assert len(native) == 1                      # one account, listed once
    pos = native[0]
    assert pos["wallet_id"] == 2                 # primary = first wallet
    assert [w["wallet_id"] for w in pos["wallets"]] == [2, 3]
    assert all(w["value_usd"] is None for w in pos["wallets"])  # can't split an account
    assert pos["delegated_usd"] == pytest.approx(1000.0 * ADA_PRICE)
    # additive split so clients never add delegated ADA on top of wallet value
    assert out["native_delegation_usd"] == pytest.approx(1000.0 * ADA_PRICE, abs=0.01)
    assert out["protocol_staked_usd"] == 0
    assert out["total_staked_usd"] == pytest.approx(out["native_delegation_usd"])
