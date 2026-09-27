"""
Unit tests for ABCT-BF-KEY-UNIFY-2026-09-27.

Bug: backend/services/defi.py, backend/routers/defi.py,
backend/routers/custom_tokens.py and backend/routers/nfts.py (plus, found by
the same audit, backend/services/nft.py and every Cardano DeFi protocol
adapter under backend/services/defi_protocols/cardano/) read
BLOCKFROST_API_KEY directly from config.py — a process-start env-var read —
instead of going through APIKeyManager, which checks the database-stored key
(settable from the Settings page) first and falls back to the env var.

Production runs with the env var deliberately BLANK (user decision AI-0016)
and the real key stored in the DB, so every one of these paths called
hosted Blockfrost with an empty key and got 403s — observed live in the
2026-09-26 N5 drill when the self-hosted backend was down.

These tests mock the database layer and HTTP calls — no live network calls,
no real keys.
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import services.api_key_manager as api_key_manager_module  # noqa: E402
from services.api_key_manager import APIKeyManager  # noqa: E402


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = str(self._json)

    def json(self):
        return self._json


# ---------------------------------------------------------------------------
# 1. Core precedence: APIKeyManager itself (the shared component every fixed
#    call site now goes through).
# ---------------------------------------------------------------------------


class TestAPIKeyManagerPrecedence:
    """DB-stored key wins; env var is the fallback; a fresh instance re-reads
    both each time its 60s cache has expired (no import-time freezing)."""

    @pytest.mark.asyncio
    async def test_db_key_used_when_env_blank(self, monkeypatch):
        monkeypatch.delenv("BLOCKFROST_API_KEY", raising=False)

        async def fake_get_api_key(api_name, user_id=1):
            assert api_name == "blockfrost"
            return "db-stored-key"

        monkeypatch.setattr(api_key_manager_module, "get_api_key", fake_get_api_key)

        mgr = APIKeyManager("blockfrost", "BLOCKFROST_API_KEY")
        key = await mgr.get_api_key()
        assert key == "db-stored-key"

    @pytest.mark.asyncio
    async def test_env_used_when_no_db_key(self, monkeypatch):
        monkeypatch.setenv("BLOCKFROST_API_KEY", "env-fallback-key")

        async def fake_get_api_key(api_name, user_id=1):
            return ""  # nothing saved in Settings

        monkeypatch.setattr(api_key_manager_module, "get_api_key", fake_get_api_key)

        mgr = APIKeyManager("blockfrost", "BLOCKFROST_API_KEY")
        key = await mgr.get_api_key()
        assert key == "env-fallback-key"

    @pytest.mark.asyncio
    async def test_db_wins_when_both_set(self, monkeypatch):
        monkeypatch.setenv("BLOCKFROST_API_KEY", "env-key-should-be-ignored")

        async def fake_get_api_key(api_name, user_id=1):
            return "db-key-should-win"

        monkeypatch.setattr(api_key_manager_module, "get_api_key", fake_get_api_key)

        mgr = APIKeyManager("blockfrost", "BLOCKFROST_API_KEY")
        key = await mgr.get_api_key()
        assert key == "db-key-should-win"

    @pytest.mark.asyncio
    async def test_neither_configured_returns_empty(self, monkeypatch):
        monkeypatch.delenv("BLOCKFROST_API_KEY", raising=False)

        async def fake_get_api_key(api_name, user_id=1):
            return ""

        monkeypatch.setattr(api_key_manager_module, "get_api_key", fake_get_api_key)

        mgr = APIKeyManager("blockfrost", "BLOCKFROST_API_KEY")
        key = await mgr.get_api_key()
        assert key == ""

    @pytest.mark.asyncio
    async def test_not_cached_at_import_time_settings_change_takes_effect(self, monkeypatch):
        """
        A key saved via Settings must take effect without a restart: the
        manager re-checks the DB per request (subject only to its own short
        TTL cache), never freezing the value it saw at import/init time.
        """
        monkeypatch.delenv("BLOCKFROST_API_KEY", raising=False)
        state = {"db_key": ""}

        async def fake_get_api_key(api_name, user_id=1):
            return state["db_key"]

        monkeypatch.setattr(api_key_manager_module, "get_api_key", fake_get_api_key)

        mgr = APIKeyManager("blockfrost", "BLOCKFROST_API_KEY", cache_ttl_seconds=0)
        assert await mgr.get_api_key() == ""

        # User saves a key on the Settings page.
        state["db_key"] = "freshly-saved-key"
        assert await mgr.get_api_key() == "freshly-saved-key"


# ---------------------------------------------------------------------------
# 2. services/defi.py — DeFiService._get_headers()
# ---------------------------------------------------------------------------


class TestDefiServiceHeaders:
    @pytest.mark.asyncio
    async def test_uses_db_key_when_env_blank(self, monkeypatch):
        import services.defi as defi_module

        monkeypatch.delenv("BLOCKFROST_API_KEY", raising=False)
        monkeypatch.setattr(
            defi_module, "_blockfrost_keys",
            APIKeyManager("blockfrost", "BLOCKFROST_API_KEY"),
        )

        async def fake_get_api_key(api_name, user_id=1):
            return "db-key"

        monkeypatch.setattr(api_key_manager_module, "get_api_key", fake_get_api_key)

        svc = defi_module.DeFiService()
        headers = await svc._get_headers()
        assert headers == {"project_id": "db-key"}

    @pytest.mark.asyncio
    async def test_falls_back_to_env_when_no_db_key(self, monkeypatch):
        import services.defi as defi_module

        monkeypatch.setenv("BLOCKFROST_API_KEY", "env-key")
        monkeypatch.setattr(
            defi_module, "_blockfrost_keys",
            APIKeyManager("blockfrost", "BLOCKFROST_API_KEY"),
        )

        async def fake_get_api_key(api_name, user_id=1):
            return ""

        monkeypatch.setattr(api_key_manager_module, "get_api_key", fake_get_api_key)

        svc = defi_module.DeFiService()
        headers = await svc._get_headers()
        assert headers == {"project_id": "env-key"}


# ---------------------------------------------------------------------------
# 3. routers/custom_tokens.py — lookup_cardano_token()
#
# This is the exact regression the bug caused: the old code did
# `if not BLOCKFROST_API_KEY: return None` and bailed out immediately,
# even when a key was saved in the DB.
# ---------------------------------------------------------------------------


class TestCustomTokensLookup:
    @pytest.mark.asyncio
    async def test_lookup_proceeds_with_db_key_when_env_blank(self, monkeypatch):
        import services.http_client as http_client_module
        import routers.custom_tokens as ct_router

        monkeypatch.delenv("BLOCKFROST_API_KEY", raising=False)
        monkeypatch.setattr(
            ct_router, "_blockfrost_keys",
            APIKeyManager("blockfrost", "BLOCKFROST_API_KEY"),
        )

        async def fake_get_api_key(api_name, user_id=1):
            return "db-key"

        monkeypatch.setattr(api_key_manager_module, "get_api_key", fake_get_api_key)

        captured = {}

        async def fake_blockfrost_fetch(path, *, headers=None, timeout=30.0, **kw):
            captured["headers"] = headers
            return FakeResponse(200, {
                "policy_id": "abc123", "asset_name": "546f6b656e",
                "onchain_metadata": {"name": "Token", "ticker": None},
            })

        monkeypatch.setattr(http_client_module, "blockfrost_fetch", fake_blockfrost_fetch)

        result = await ct_router.lookup_cardano_token("abc123", "546f6b656e")

        assert result is not None
        assert captured["headers"] == {"project_id": "db-key"}

    @pytest.mark.asyncio
    async def test_lookup_returns_none_when_no_key_anywhere(self, monkeypatch):
        """Old bug's early-return is still correct when there's truly no key
        anywhere — it just must not fire when only the env var is blank."""
        import routers.custom_tokens as ct_router

        monkeypatch.delenv("BLOCKFROST_API_KEY", raising=False)
        monkeypatch.setattr(
            ct_router, "_blockfrost_keys",
            APIKeyManager("blockfrost", "BLOCKFROST_API_KEY"),
        )

        async def fake_get_api_key(api_name, user_id=1):
            return ""

        monkeypatch.setattr(api_key_manager_module, "get_api_key", fake_get_api_key)

        result = await ct_router.lookup_cardano_token("abc123", "546f6b656e")
        assert result is None


# ---------------------------------------------------------------------------
# 4. routers/nfts.py — Blockfrost onchain-metadata fallback in
#    get_nft_wall_details()
# ---------------------------------------------------------------------------


class TestNftsBlockfrostFallback:
    @pytest.mark.asyncio
    async def test_wall_details_blockfrost_fallback_uses_db_key(self, monkeypatch):
        import services.http_client as http_client_module
        import routers.nfts as nfts_router

        monkeypatch.delenv("BLOCKFROST_API_KEY", raising=False)
        monkeypatch.setattr(
            nfts_router, "_blockfrost_keys",
            APIKeyManager("blockfrost", "BLOCKFROST_API_KEY"),
        )

        async def fake_get_api_key(api_name, user_id=1):
            return "db-key"

        monkeypatch.setattr(api_key_manager_module, "get_api_key", fake_get_api_key)

        asset_id = "a" * 56 + "b" * 8

        async def fake_get_all_nfts(user_id, force_refresh=False):
            return [{"unit": asset_id, "asset_id": asset_id}]

        monkeypatch.setattr(nfts_router.nft_service, "get_all_nfts", fake_get_all_nfts)

        class DummyMetaService:
            async def is_configured(self):
                return False

            async def get_nft_metadata(self, *a, **kw):
                return None

        captured = {}

        async def fake_blockfrost_fetch(path, *, headers=None, timeout=30.0, **kw):
            captured["headers"] = headers
            return FakeResponse(200, {"onchain_metadata": {"name": "NFT #1"}})

        monkeypatch.setattr(http_client_module, "blockfrost_fetch", fake_blockfrost_fetch)

        # The handler does `from services.nftcdn import nftcdn_service` (and
        # nmkr) locally at call time, so patch the source modules rather
        # than routers.nfts's own namespace.
        import services.nftcdn as nftcdn_module
        import services.nmkr as nmkr_module
        monkeypatch.setattr(nftcdn_module, "nftcdn_service", DummyMetaService())
        monkeypatch.setattr(nmkr_module, "nmkr_service", DummyMetaService())

        # Everything past the Blockfrost fallback (wallet name lookup,
        # collection siblings, ...) needs a real DB and isn't what this bug
        # is about; we only care that the fallback request carried the
        # resolved key, so tolerate the downstream 500 once that's captured.
        from fastapi import HTTPException
        try:
            await nfts_router.get_nft_wall_details("cardano", asset_id, user_id=1)
        except HTTPException:
            pass

        assert captured["headers"] == {"project_id": "db-key"}


# ---------------------------------------------------------------------------
# 5. services/defi_protocols/cardano/utils.py — get_blockfrost_headers(),
#    shared by iagon.py, surf.py, liqwid.py and strike.py.
# ---------------------------------------------------------------------------


class TestCardanoDefiProtocolSharedHeaders:
    @pytest.mark.asyncio
    async def test_db_first_env_fallback(self, monkeypatch):
        import services.defi_protocols.cardano.utils as cdp_utils

        monkeypatch.setattr(
            cdp_utils, "_blockfrost_keys",
            APIKeyManager("blockfrost", "BLOCKFROST_API_KEY"),
        )

        # DB set, env blank -> DB wins
        monkeypatch.delenv("BLOCKFROST_API_KEY", raising=False)

        async def fake_get_api_key(api_name, user_id=1):
            return "db-key"

        monkeypatch.setattr(api_key_manager_module, "get_api_key", fake_get_api_key)
        assert await cdp_utils.get_blockfrost_headers() == {"project_id": "db-key"}

        # DB blank, env set -> env fallback
        cdp_utils._blockfrost_keys.clear_cache()
        monkeypatch.setenv("BLOCKFROST_API_KEY", "env-key")

        async def fake_get_api_key_empty(api_name, user_id=1):
            return ""

        monkeypatch.setattr(api_key_manager_module, "get_api_key", fake_get_api_key_empty)
        assert await cdp_utils.get_blockfrost_headers() == {"project_id": "env-key"}

    @pytest.mark.asyncio
    async def test_liqwid_adapter_builds_request_with_resolved_key(self, monkeypatch):
        """Spot-check one adapter actually goes through the shared helper
        end to end (liqwid.py was one of the affected files)."""
        import services.defi_protocols.cardano.utils as cdp_utils
        import services.defi_protocols.cardano.liqwid as liqwid_module

        monkeypatch.setattr(
            cdp_utils, "_blockfrost_keys",
            APIKeyManager("blockfrost", "BLOCKFROST_API_KEY"),
        )
        monkeypatch.delenv("BLOCKFROST_API_KEY", raising=False)

        async def fake_get_api_key(api_name, user_id=1):
            return "db-key"

        monkeypatch.setattr(api_key_manager_module, "get_api_key", fake_get_api_key)

        captured = {}

        async def fake_blockfrost_fetch(path, *, headers=None, timeout=15.0, **kw):
            captured["headers"] = headers
            # Empty first page -> adapter returns early, so exactly one
            # call is made and there's nothing else to mock.
            return FakeResponse(200, [])

        monkeypatch.setattr(liqwid_module, "blockfrost_fetch", fake_blockfrost_fetch)

        adapter = liqwid_module.LiqwidAdapter()
        addr = "addr1qx2fxv2umyhttkxyxp8x0dlpdt3k6cwng5pxj3jhsydzer3n0d3vllmyqwsx5wktcd8cc3sq835lu7drv2xwl2wywfgse35a3x"
        result = await adapter._detect_staking(addr)

        assert result == []
        assert captured.get("headers") == {"project_id": "db-key"}


# ---------------------------------------------------------------------------
# 6. strike.py — the `self.headers` AttributeError this audit also found
#    (pre-existing, adjacent to the key-precedence bug: pending rewards
#    always silently returned None).
# ---------------------------------------------------------------------------


class TestStrikeAdapterHeadersFix:
    @pytest.mark.asyncio
    async def test_get_pending_rewards_no_longer_crashes_on_missing_headers(self, monkeypatch):
        import services.defi_protocols.cardano.utils as cdp_utils
        import services.defi_protocols.cardano.strike as strike_module

        monkeypatch.setattr(
            cdp_utils, "_blockfrost_keys",
            APIKeyManager("blockfrost", "BLOCKFROST_API_KEY"),
        )
        monkeypatch.delenv("BLOCKFROST_API_KEY", raising=False)

        async def fake_get_api_key(api_name, user_id=1):
            return "db-key"

        monkeypatch.setattr(api_key_manager_module, "get_api_key", fake_get_api_key)

        captured = {}

        async def fake_blockfrost_fetch(path, *, headers=None, timeout=30.0, **kw):
            captured["headers"] = headers
            return FakeResponse(200, [])

        monkeypatch.setattr(strike_module, "blockfrost_fetch", fake_blockfrost_fetch)
        monkeypatch.setattr(strike_module, "get_client", lambda *a, **kw: object())

        addr = "addr1qx2fxv2umyhttkxyxp8x0dlpdt3k6cwng5pxj3jhsydzer3n0d3vllmyqwsx5wktcd8cc3sq835lu7drv2xwl2wywfgse35a3x"
        adapter = strike_module.StrikeAdapter()
        result = await adapter.get_pending_rewards(addr)

        # Before the fix, `self.headers` raised AttributeError, was caught
        # by the broad except, and this was always None.
        assert result is not None
        assert result["pending_rewards"] == 0
        assert captured["headers"] == {"project_id": "db-key"}


# ---------------------------------------------------------------------------
# 7. Fallback-to-hosted path sends the key: when the self-hosted (RYO)
#    Blockfrost is down and blockfrost_fetch falls back to the external
#    hosted API, the resolved key must still be sent on the fallback call.
# ---------------------------------------------------------------------------


class TestFallbackToHostedSendsKey:
    @pytest.mark.asyncio
    async def test_headers_carried_through_ryo_to_external_fallback(self, monkeypatch):
        import httpx
        from unittest.mock import AsyncMock, MagicMock
        import services.http_client as http_client_module
        import services.defi as defi_module

        monkeypatch.delenv("BLOCKFROST_API_KEY", raising=False)
        monkeypatch.setattr(
            defi_module, "_blockfrost_keys",
            APIKeyManager("blockfrost", "BLOCKFROST_API_KEY"),
        )

        async def fake_get_api_key(api_name, user_id=1):
            return "db-key"

        monkeypatch.setattr(api_key_manager_module, "get_api_key", fake_get_api_key)

        svc = defi_module.DeFiService()
        headers = await svc._get_headers()
        assert headers == {"project_id": "db-key"}

        ryo_url = "http://192.0.2.10:3000"
        ext_url = "https://cardano-mainnet.blockfrost.io/api/v0"

        mock_client = AsyncMock()
        primary_response = MagicMock(spec=httpx.Response)
        primary_response.status_code = 500
        fallback_response = MagicMock(spec=httpx.Response)
        fallback_response.status_code = 200
        mock_client.request = AsyncMock(side_effect=[primary_response, fallback_response])

        monkeypatch.setattr(http_client_module, "get_client", lambda *a, **kw: mock_client)
        monkeypatch.setattr("config.BLOCKFROST_BASE_URL", ryo_url, raising=False)
        monkeypatch.setattr("config.BLOCKFROST_EXTERNAL_URL", ext_url, raising=False)

        resp = await http_client_module.blockfrost_fetch(
            "/addresses/addr1test/utxos", headers=headers, timeout=30.0
        )

        assert resp.status_code == 200
        assert mock_client.request.call_count == 2
        for call in mock_client.request.call_args_list:
            assert call.kwargs.get("headers") == {"project_id": "db-key"}
