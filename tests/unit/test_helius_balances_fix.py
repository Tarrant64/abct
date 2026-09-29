"""
Unit tests for ABCT-HELIUS-BALANCES-FIX-2026-09-28.

Helius retired the v0 REST `/addresses/{address}/balances` endpoint
(SolanaService.get_address_info used it, and the Settings health/test
check for "helius" also used it). Both now returned HTTP 404 "Method not
found", so Solana wallet balances failed and the Settings page showed
Helius as failing even though Helius NFT (DAS) fetches still worked.

Fix:
  - services/solana.py `get_address_info()` now calls the Helius DAS
    `searchAssets` JSON-RPC method (tokenType="fungible",
    displayOptions.showNativeBalance) instead of the retired REST
    endpoint, keeping the same output shape (balance_sol, balance_lamports,
    tokens[] with mint/symbol/name/balance/amount_raw/decimals, source).
  - services/api_health.py "helius" health test now POSTs a plain Solana
    `getHealth` JSON-RPC call against the Helius RPC endpoint instead of
    hitting the retired balances endpoint.

All HTTP and DB access is mocked: no network, no real keys, no real
addresses (fake base58-shaped addresses only).
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Fake, non-real Solana-address-shaped strings (base58, 32-44 chars). They
# must stay base58-valid: SolanaService.is_solana_address() runs for real
# in these tests (only get_api_key/is_configured are mocked) and gates
# get_address_info(), so an invalid shape would short-circuit before the
# code under test ever runs. Allowlisted in sec/wallet_allowlist.txt,
# same convention as the existing DemoSo1ana*/JUPyiw... synthetic entries.
WALLET_A = "So1anaFakeWa11etAddressForTests111111111"
WALLET_B = "So1anaFakeWa11etAddressForTestsBBBBBBBBBB"


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text or str(self._json)

    def json(self):
        return self._json


class RecordingClient:
    """Stands in for the shared httpx client; records posted payloads."""

    def __init__(self, response_or_fn):
        self._response = response_or_fn
        self.calls = []

    async def post(self, url, json=None, **kwargs):
        self.calls.append({"url": url, "json": json})
        if callable(self._response):
            return self._response(url, json)
        return self._response

    async def get(self, url, params=None, **kwargs):
        self.calls.append({"url": url, "params": params})
        if callable(self._response):
            return self._response(url, params)
        return self._response


# ---------------------------------------------------------------------------
# services/solana.py — get_address_info() balances fetch
# ---------------------------------------------------------------------------

@pytest.fixture
def solana_service(monkeypatch):
    import services.solana as mod

    svc = mod.SolanaService()

    async def fake_get_api_key(self=None, user_id=1):
        return "test-key-not-real"

    async def fake_is_configured():
        return True

    monkeypatch.setattr(mod.SolanaService, "get_api_key", fake_get_api_key)
    monkeypatch.setattr(svc, "is_configured", fake_is_configured)
    return mod, svc


def _das_result(native_lamports, items):
    return {
        "jsonrpc": "2.0",
        "id": "x",
        "result": {
            "total": len(items),
            "nativeBalance": {"lamports": native_lamports, "price_per_sol": 150.0,
                               "total_price": native_lamports / 1_000_000_000 * 150.0},
            "items": items,
        },
    }


def _fungible_item(mint, symbol, name, balance_raw, decimals):
    return {
        "interface": "FungibleToken",
        "id": mint,
        "content": {"metadata": {"name": name, "symbol": symbol}},
        "token_info": {
            "symbol": symbol,
            "balance": balance_raw,
            "decimals": decimals,
            "token_program": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
        },
    }


async def test_get_address_info_sol_only(solana_service, monkeypatch):
    mod, svc = solana_service
    resp = FakeResponse(200, _das_result(2_500_000_000, []))
    client = RecordingClient(resp)
    monkeypatch.setattr(mod, "get_client", lambda *a, **k: client)

    info = await svc.get_address_info(WALLET_A)

    assert info["source"] == "helius"
    assert info["balance_lamports"] == 2_500_000_000
    assert info["balance_sol"] == pytest.approx(2.5)
    assert info["tokens"] == []
    assert info["token_count"] == 0

    # Uses the DAS searchAssets JSON-RPC method, not the retired REST endpoint
    call = client.calls[0]
    assert "/addresses/" not in call["url"] and "/balances" not in call["url"]
    assert call["json"]["method"] == "searchAssets"
    assert call["json"]["params"]["tokenType"] == "fungible"
    assert call["json"]["params"]["displayOptions"]["showNativeBalance"] is True


async def test_get_address_info_sol_plus_spl_tokens(solana_service, monkeypatch):
    mod, svc = solana_service
    items = [
        _fungible_item("Mint111USDCFake11111111111111111111111111", "USDC", "USD Coin",
                        100_000_000, 6),
        _fungible_item("Mint222JitoSOLFake111111111111111111111111", "JitoSOL", "Jito Staked SOL",
                        35_688_813_508, 9),
    ]
    resp = FakeResponse(200, _das_result(1_000_000_000, items))
    client = RecordingClient(resp)
    monkeypatch.setattr(mod, "get_client", lambda *a, **k: client)

    info = await svc.get_address_info(WALLET_A)

    assert info["balance_sol"] == pytest.approx(1.0)
    assert info["token_count"] == 2
    by_symbol = {t["symbol"]: t for t in info["tokens"]}
    assert by_symbol["USDC"]["balance"] == pytest.approx(100.0)
    assert by_symbol["USDC"]["amount_raw"] == 100_000_000
    assert by_symbol["USDC"]["decimals"] == 6
    assert by_symbol["JitoSOL"]["balance"] == pytest.approx(35.688813508)
    assert by_symbol["JitoSOL"]["name"] == "Jito Staked SOL"


# Real, public Helium (HNT) SPL mint and its on-chain decimals (public
# chain data, not a secret): used so the "correct mint and decimals" case
# is checked against the real token, not a placeholder.
HNT_MINT = "hntyVP6YFm1Hg25TN9WGLqM12b8TQmcknKrdu1oxWux"
HNT_DECIMALS = 8


async def test_get_address_info_sol_plus_hnt_newly_added_wallet(solana_service, monkeypatch):
    """Exact user-reported scenario: a newly added Solana wallet (the one
    now holding the Helium hotspot NFTs) shows the correct address but
    previously came back with 0 assets, because the retired v0 balances
    endpoint 404'd. It should show a little SOL plus an SPL token (HNT)
    with the correct mint and decimals -- not zero."""
    mod, svc = solana_service
    items = [
        _fungible_item(HNT_MINT, "HNT", "Helium Network Token", 42_50000000, HNT_DECIMALS),
    ]
    resp = FakeResponse(200, _das_result(150_000_000, items))  # 0.15 SOL
    client = RecordingClient(resp)
    monkeypatch.setattr(mod, "get_client", lambda *a, **k: client)

    info = await svc.get_address_info(WALLET_A)

    assert info["source"] == "helius"
    assert info["balance_sol"] == pytest.approx(0.15)
    assert info["token_count"] == 1
    hnt = info["tokens"][0]
    assert hnt["mint"] == HNT_MINT
    assert hnt["symbol"] == "HNT"
    assert hnt["decimals"] == HNT_DECIMALS
    assert hnt["amount_raw"] == 42_50000000
    assert hnt["balance"] == pytest.approx(42.5)


async def test_newly_added_solana_wallet_saves_sol_and_hnt_not_zero(monkeypatch):
    """End-to-end through routers.wallets._refresh_wallet_balance (the
    real code path a newly added wallet's first refresh runs): with a
    working DAS response, the wallet must be saved with its real SOL
    balance and its HNT token as a native asset with the correct mint/
    decimals -- confirming the fix reaches the UI-facing save path, not
    just the service method. Price lookup is untouched: it stays keyed
    off the 'symbol' field (unchanged) which services/pricing.py already
    maps ('HNT' -> 'helium'), so no pricing code needed to change here."""
    import routers.wallets as wallets_router
    import services.solana as solana_mod

    items = [_fungible_item(HNT_MINT, "HNT", "Helium Network Token", 42_50000000, HNT_DECIMALS)]
    resp = FakeResponse(200, _das_result(150_000_000, items))
    client = RecordingClient(resp)
    monkeypatch.setattr(solana_mod, "get_client", lambda *a, **k: client)

    async def fake_get_api_key(self=None, user_id=1):
        return "test-key-not-real"

    async def fake_is_configured():
        return True

    monkeypatch.setattr(solana_mod.SolanaService, "get_api_key", fake_get_api_key)
    monkeypatch.setattr(wallets_router.solana_service, "is_configured", fake_is_configured)

    saved_balances = []
    saved_assets = []

    async def fake_save_balance(wallet_id, amount, unit):
        saved_balances.append((wallet_id, amount, unit))

    async def fake_save_native_assets(wallet_id, assets):
        saved_assets.append((wallet_id, assets))

    monkeypatch.setattr(wallets_router, "save_balance", fake_save_balance)
    monkeypatch.setattr(wallets_router, "save_native_assets", fake_save_native_assets)

    wallet = {"id": 42, "address": WALLET_A, "blockchain": "solana", "label": "New HNT wallet"}
    result = await wallets_router._refresh_wallet_balance(wallet)

    assert result["success"] is True
    assert result["unit"] == "SOL"
    assert result["balance"] == pytest.approx(0.15)
    assert result["token_count"] == 1
    assert result["source"] == "helius"

    assert saved_balances == [(42, "0.15", "SOL")]
    assert len(saved_assets) == 1
    wallet_id, spl_assets = saved_assets[0]
    assert wallet_id == 42
    assert spl_assets == [{
        "asset_id": HNT_MINT,
        "policy_id": HNT_MINT,
        "asset_name": "HNT",
        "quantity": "4250000000",
        "decimals": HNT_DECIMALS,
    }]


async def test_get_address_info_zero_balances_all_filtered(solana_service, monkeypatch):
    mod, svc = solana_service
    items = [
        _fungible_item("Mint333ZeroFake1111111111111111111111111", "ZERO", "Zero Token", 0, 6),
    ]
    resp = FakeResponse(200, _das_result(0, items))
    client = RecordingClient(resp)
    monkeypatch.setattr(mod, "get_client", lambda *a, **k: client)

    info = await svc.get_address_info(WALLET_A)

    assert info["balance_sol"] == 0
    assert info["tokens"] == []
    assert info["token_count"] == 0


async def test_get_address_info_http_error_returns_none_gracefully(solana_service, monkeypatch):
    """A non-200 (e.g. the old 404 "Method not found") must not crash and
    must not raise — it returns None (same as pre-fix behaviour for a
    non-200 response; the caller in routers/wallets.py then reports a
    fetch failure for that wallet without wiping any existing cached
    totals). This is the exact shape of the previous production failure
    mode against the retired endpoint."""
    mod, svc = solana_service
    client = RecordingClient(FakeResponse(404, {}, text='{"error":"Method not found"}'))
    monkeypatch.setattr(mod, "get_client", lambda *a, **k: client)

    info = await svc.get_address_info(WALLET_A)

    assert info is None


async def test_get_address_info_network_exception_falls_back_to_public_rpc(solana_service, monkeypatch):
    """A network-level exception (not just a bad HTTP status) still falls
    back to public RPC, same as before the fix."""
    mod, svc = solana_service

    class RaisingClient:
        async def post(self, *a, **k):
            raise ConnectionError("boom")

    monkeypatch.setattr(mod, "get_client", lambda *a, **k: RaisingClient())

    public_rpc_calls = []

    async def fake_public_rpc(address):
        public_rpc_calls.append(address)
        return {"address": address, "balance_sol": 0.0, "balance_lamports": 0,
                "tokens": [], "token_count": 0, "source": "public_rpc"}

    monkeypatch.setattr(svc, "get_balance_from_public_rpc", fake_public_rpc)

    info = await svc.get_address_info(WALLET_A)

    assert info["source"] == "public_rpc"
    assert public_rpc_calls == [WALLET_A]


async def test_get_address_info_jsonrpc_error_returns_none_not_exception(solana_service, monkeypatch):
    """A 200 with a JSON-RPC "error" body (malformed/rejected request) must
    be treated as a failure, not silently parsed as zero balances."""
    mod, svc = solana_service
    resp = FakeResponse(200, {"jsonrpc": "2.0", "id": "x",
                               "error": {"code": -32600, "message": "Invalid request"}})
    client = RecordingClient(resp)
    monkeypatch.setattr(mod, "get_client", lambda *a, **k: client)

    info = await svc.get_address_info(WALLET_A)

    assert info is None


def test_no_source_calls_retired_v0_balances_endpoint():
    """Guard against regressing back onto the retired endpoint anywhere
    in services/. Comments/docstrings are allowed to *mention* the old
    path (they document why it was replaced); only an actual client call
    (client.get(...) or an f-string building a request URL) is checked."""
    services_dir = os.path.join(BACKEND_DIR, "services")
    offenders = []
    for fn in os.listdir(services_dir):
        if fn.endswith(".py"):
            with open(os.path.join(services_dir, fn)) as fh:
                for line in fh:
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    if "/addresses/{address}/balances" in line and ("client." in line or "f\"" in line or "f'" in line):
                        offenders.append((fn, stripped))
    assert offenders == []


# ---------------------------------------------------------------------------
# services/api_health.py — "helius" health/test check
# ---------------------------------------------------------------------------

@pytest.fixture
def health_client(monkeypatch):
    import services.api_health as mod
    return mod


async def test_helius_health_check_uses_solana_rpc_not_retired_endpoint(health_client, monkeypatch):
    mod = health_client
    api_id, config = "helius", mod.API_HEALTH_TESTS["helius"]
    assert config[0] == "solana_rpc"
    assert "/addresses/" not in config[1] and "/balances" not in config[1]
    assert "mainnet.helius-rpc.com" in config[1]

    client = RecordingClient(FakeResponse(200, {"jsonrpc": "2.0", "id": 1, "result": "ok"}))
    monkeypatch.setattr(mod, "get_client", lambda *a, **k: client)

    result = await mod.run_api_test(api_id, api_key="test-key-not-real")

    assert result["success"] is True
    assert result["tested"] is True
    assert client.calls[0]["json"]["method"] == "getHealth"


async def test_helius_health_check_reports_failure_on_error(health_client, monkeypatch):
    mod = health_client
    client = RecordingClient(FakeResponse(404, {}, text="Method not found"))
    monkeypatch.setattr(mod, "get_client", lambda *a, **k: client)

    result = await mod.run_api_test("helius", api_key="test-key-not-real")

    assert result["success"] is False
    assert result["tested"] is True
    assert "404" in result["message"]
