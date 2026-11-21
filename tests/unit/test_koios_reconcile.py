"""services/koios_reconcile.py: correct (POST) Koios endpoints, local stake derivation,
no /resolve_address, lovelace parsing, fallback on Koios error, Blockfrost equivalence."""
import json
import os
import sys

import httpx
import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from services import koios_reconcile  # noqa: E402
from services.koios_reconcile import WalletReconciliationService  # noqa: E402

# Public mainnet base address and its real stake address (verified against Koios address_info).
ADDR = "addr1qx2fxv2umyhttkxyxp8x0dlpdt3k6cwng5pxj3jhsydzer3n0d3vllmyqwsx5wktcd8cc3sq835lu7drv2xwl2wywfgse35a3x"
STAKE = "stake1uyehkck0lajq8gr28t9uxnuvgcqrc6070x3k9r8048z8y5gh6ffgw"

ACCOUNT_INFO = [{"stake_address": STAKE, "status": "registered", "total_balance": "38351090835",
                 "utxo": "36958050955", "rewards_available": "1393039880"}]
ACCOUNT_ASSETS = [
    {"stake_address": STAKE, "policy_id": "aa" * 28, "asset_name": "534e454b", "decimals": 0, "quantity": "14941628"},
    {"stake_address": STAKE, "policy_id": "bb" * 28, "asset_name": "4c51", "decimals": 6, "quantity": "2500000"},
    {"stake_address": STAKE, "policy_id": "cc" * 28, "asset_name": "6e6674", "decimals": 0, "quantity": "1"},
]


def make_service(handler):
    svc = WalletReconciliationService()
    svc._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return svc


def good_handler(calls):
    def handler(request: httpx.Request):
        body = json.loads(request.content or b"{}")
        calls.append((request.method, request.url.path, body))
        if request.url.path.endswith("/account_info"):
            return httpx.Response(200, json=ACCOUNT_INFO)
        if request.url.path.endswith("/account_assets"):
            return httpx.Response(200, json=ACCOUNT_ASSETS)
        return httpx.Response(404, json={})
    return handler


async def test_uses_real_post_endpoints_and_never_resolve_address():
    calls = []
    svc = make_service(good_handler(calls))
    out = await svc.get_wallet_portfolio(ADDR)
    assert out and out["stake_address"] == STAKE
    assert {c[0] for c in calls} == {"POST"}
    assert {c[1].rsplit("/", 1)[-1] for c in calls} == {"account_info", "account_assets"}
    assert all(c[2] == {"_stake_addresses": [STAKE]} for c in calls)
    assert not any("resolve_address" in c[1] for c in calls)
    await svc.close()


async def test_parses_lovelace_and_assets():
    svc = make_service(good_handler([]))
    out = await svc.get_wallet_portfolio(ADDR)
    assert out["utxo_ada"] == pytest.approx(36958.050955)
    assert out["ada_balance"] == out["utxo_ada"]
    assert out["rewards_available_ada"] == pytest.approx(1393.039880)
    assert out["total_balance_ada"] == pytest.approx(38351.090835)
    by_name = {p["asset_name"]: p for p in out["positions"]}
    assert by_name["534e454b"]["raw_quantity"] == 14941628
    assert by_name["534e454b"]["unit"] == "aa" * 28 + "534e454b"
    assert by_name["4c51"]["balance"] == pytest.approx(2.5) and by_name["4c51"]["decimals"] == 6
    assert out["num_tokens"] == 2 and out["num_nfts"] == 1
    await svc.close()


async def test_stake_derivation_is_local_no_network():
    calls = []
    svc = make_service(good_handler(calls))
    assert await svc._address_to_stake(ADDR) == STAKE
    assert calls == []
    await svc.close()


async def test_address_info_fallback_for_non_derivable_address():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json=[{"address": "x", "stake_address": STAKE}])

    svc = make_service(handler)
    assert await svc._address_to_stake("addr1_not_derivable") == STAKE
    assert calls == ["/api/v1/address_info"]
    await svc.close()


async def test_koios_error_returns_none_for_caller_fallback():
    svc = make_service(lambda r: httpx.Response(503, text="down"))
    assert await svc.get_wallet_portfolio(ADDR) is None
    await svc.close()


async def test_assets_paginate():
    pages = []

    def handler(request):
        if request.url.path.endswith("/account_info"):
            return httpx.Response(200, json=ACCOUNT_INFO)
        off = int(request.url.params.get("offset", 0))
        pages.append(off)
        n = 1000 if off == 0 else 5
        return httpx.Response(200, json=[
            {"policy_id": "dd" * 28, "asset_name": f"{off + i:08x}", "decimals": 0, "quantity": "7"}
            for i in range(n)])

    svc = make_service(handler)
    out = await svc.get_wallet_portfolio(ADDR)
    assert pages == [0, 1000] and len(out["positions"]) == 1005
    await svc.close()


async def test_koios_and_blockfrost_fallback_agree_on_ada(monkeypatch):
    """Same account data via Koios (utxo) and via the Blockfrost fallback
    (controlled - withdrawable) must give the same spendable ADA."""
    svc = make_service(good_handler([]))
    koios_ada = (await svc.get_wallet_portfolio(ADDR))["utxo_ada"]
    await svc.close()

    from services.cardano import cardano_service

    async def fake_info(stake):
        return {"controlled_ada": 38351.090835, "withdrawable_ada": 1393.039880}

    monkeypatch.setattr(cardano_service, "get_stake_account_info", fake_info)
    bf_ada = await cardano_service.get_account_utxo_ada(STAKE)
    assert bf_ada == pytest.approx(koios_ada)


def test_old_module_name_is_a_shim():
    from services import taptools
    assert taptools.taptools_wallet_service is koios_reconcile.taptools_wallet_service
