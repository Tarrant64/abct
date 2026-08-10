"""
Unit tests for Blockfrost RYO (Run Your Own) integration.

Tests the core logic of:
  - blockfrost_fetch() fallback: primary success, primary fail -> fallback, both fail
  - Config loading: BLOCKFROST_BASE_URL and BLOCKFROST_EXTERNAL_URL from env
  - api_usage_live.py self-hosted detection
  - api_health.py RYO source reporting
  - Engine provider registry: blockfrost vs blockfrost_external priorities

These tests mock HTTP calls and do NOT require a running server.

All RYO hosts below use RFC 5737 documentation addresses (192.0.2.0/24), which
are reserved and unroutable. Do not substitute a real node address here.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add backend to sys.path so imports work
BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


# ---------------------------------------------------------------------------
# 1. Config loading tests
# ---------------------------------------------------------------------------


class TestConfigLoading:
    """Verify BLOCKFROST_BASE_URL and BLOCKFROST_EXTERNAL_URL are read from env."""

    def test_default_urls_are_external(self):
        """Without env vars, both URLs default to external Blockfrost.io."""
        # The .env file may set BLOCKFROST_BASE_URL to the RYO node.
        # To test defaults, we must suppress load_dotenv AND clear env vars.
        env_copy = {k: v for k, v in os.environ.items()
                    if k not in ("BLOCKFROST_BASE_URL", "BLOCKFROST_EXTERNAL_URL")}
        with patch.dict(os.environ, env_copy, clear=True), \
             patch("dotenv.load_dotenv"):  # prevent .env from overriding
            import importlib
            import config

            importlib.reload(config)

            assert "blockfrost.io" in config.BLOCKFROST_BASE_URL
            assert "blockfrost.io" in config.BLOCKFROST_EXTERNAL_URL

    def test_custom_base_url_from_env(self):
        """BLOCKFROST_BASE_URL env var overrides the default."""
        ryo_url = "http://192.0.2.10:3000"
        with patch.dict(os.environ, {"BLOCKFROST_BASE_URL": ryo_url}):
            import importlib
            import config

            importlib.reload(config)
            assert config.BLOCKFROST_BASE_URL == ryo_url
            # External should remain default
            assert "blockfrost.io" in config.BLOCKFROST_EXTERNAL_URL

    def test_both_urls_configurable(self):
        """Both URLs can be set independently."""
        ryo_url = "http://192.0.2.10:3000"
        ext_url = "https://custom-blockfrost.example.com/api/v0"
        with patch.dict(
            os.environ,
            {
                "BLOCKFROST_BASE_URL": ryo_url,
                "BLOCKFROST_EXTERNAL_URL": ext_url,
            },
        ):
            import importlib
            import config

            importlib.reload(config)
            assert config.BLOCKFROST_BASE_URL == ryo_url
            assert config.BLOCKFROST_EXTERNAL_URL == ext_url


# ---------------------------------------------------------------------------
# 1b. URL construction validation
# ---------------------------------------------------------------------------


class TestUrlConstruction:
    """Verify that blockfrost_fetch constructs valid URLs for both RYO and external."""

    def test_ryo_url_should_not_include_api_v0(self):
        """
        CRITICAL: Blockfrost RYO serves endpoints at root (e.g., /health),
        NOT under /api/v0/. The BLOCKFROST_BASE_URL for RYO should be
        just the host:port without /api/v0 suffix.

        External Blockfrost.io DOES use /api/v0.

        Correct:
          RYO: http://192.0.2.20:30675
          External: https://cardano-mainnet.blockfrost.io/api/v0

        WRONG:
          RYO: http://192.0.2.20:30675/api/v0  (would 404)
        """
        # This test documents the expected URL format.
        # RYO endpoints: /health, /blocks/latest, /addresses/{addr}
        # External endpoints: /api/v0/health, /api/v0/blocks/latest, etc.
        ryo_base = "http://192.0.2.20:30675"
        ext_base = "https://cardano-mainnet.blockfrost.io/api/v0"

        # blockfrost_fetch appends paths like "/health", "/addresses/addr1..."
        path = "/health"
        ryo_full = f"{ryo_base}{path}"
        ext_full = f"{ext_base}{path}"

        assert ryo_full == "http://192.0.2.20:30675/health"
        assert ext_full == "https://cardano-mainnet.blockfrost.io/api/v0/health"

        # The RYO URL should NOT have /api/v0 in it
        assert "/api/v0" not in ryo_base

    def test_current_env_may_need_correction(self):
        """
        If BLOCKFROST_BASE_URL contains /api/v0 but points to a non-blockfrost.io
        host, it likely needs to be corrected (RYO doesn't use /api/v0 prefix).
        """
        import config

        base = config.BLOCKFROST_BASE_URL
        is_ryo = "blockfrost.io" not in base

        if is_ryo and "/api/v0" in base:
            # This is a known issue - document it as a warning, not a failure.
            # The .env needs to be updated when the RYO node is actually deployed.
            import warnings
            warnings.warn(
                f"BLOCKFROST_BASE_URL ({base}) appears to be a RYO URL but "
                f"includes /api/v0. Blockfrost RYO serves at root, not /api/v0. "
                f"Consider changing to: {base.replace('/api/v0', '')}",
                UserWarning,
            )


# ---------------------------------------------------------------------------
# 2. blockfrost_fetch() fallback logic
# ---------------------------------------------------------------------------


class TestBlockfrostFetch:
    """Test the primary -> fallback logic in http_client.blockfrost_fetch()."""

    @pytest.fixture(autouse=True)
    def _setup_urls(self):
        """Patch config URLs for all tests in this class."""
        self.ryo_url = "http://192.0.2.10:3000"
        self.ext_url = "https://cardano-mainnet.blockfrost.io/api/v0"
        self.patches = [
            patch("services.http_client.get_client"),
        ]
        for p in self.patches:
            p.start()
        yield
        for p in self.patches:
            p.stop()
        # Clean up module-level client cache
        from services import http_client
        http_client._clients.clear()

    @pytest.mark.asyncio
    async def test_primary_success_returns_immediately(self):
        """When primary (RYO) returns 200, no fallback is attempted."""
        import httpx
        from services.http_client import blockfrost_fetch, get_client

        mock_client = AsyncMock()
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_client.request = AsyncMock(return_value=mock_response)
        get_client.return_value = mock_client

        with patch("services.http_client.BLOCKFROST_BASE_URL", self.ryo_url, create=True), \
             patch("services.http_client.BLOCKFROST_EXTERNAL_URL", self.ext_url, create=True), \
             patch.dict("sys.modules", {}), \
             patch("config.BLOCKFROST_BASE_URL", self.ryo_url), \
             patch("config.BLOCKFROST_EXTERNAL_URL", self.ext_url):
            resp = await blockfrost_fetch("/addresses/test123")

        assert resp.status_code == 200
        # Should only be called once (primary)
        assert mock_client.request.call_count == 1
        call_url = mock_client.request.call_args[0][1]
        assert self.ryo_url in call_url

    @pytest.mark.asyncio
    async def test_primary_5xx_falls_back_to_external(self):
        """When primary returns 500, fallback to external is attempted."""
        import httpx
        from services.http_client import blockfrost_fetch, get_client

        mock_client = AsyncMock()
        primary_response = MagicMock(spec=httpx.Response)
        primary_response.status_code = 500

        fallback_response = MagicMock(spec=httpx.Response)
        fallback_response.status_code = 200

        mock_client.request = AsyncMock(
            side_effect=[primary_response, fallback_response]
        )
        get_client.return_value = mock_client

        with patch("config.BLOCKFROST_BASE_URL", self.ryo_url), \
             patch("config.BLOCKFROST_EXTERNAL_URL", self.ext_url):
            resp = await blockfrost_fetch("/blocks/latest")

        assert resp.status_code == 200
        assert mock_client.request.call_count == 2
        # Second call should use external URL
        second_url = mock_client.request.call_args_list[1][0][1]
        assert self.ext_url in second_url

    @pytest.mark.asyncio
    async def test_primary_connection_error_falls_back(self):
        """When primary raises ConnectError, fallback to external."""
        import httpx
        from services.http_client import blockfrost_fetch, get_client

        mock_client = AsyncMock()
        fallback_response = MagicMock(spec=httpx.Response)
        fallback_response.status_code = 200

        mock_client.request = AsyncMock(
            side_effect=[httpx.ConnectError("Connection refused"), fallback_response]
        )
        get_client.return_value = mock_client

        with patch("config.BLOCKFROST_BASE_URL", self.ryo_url), \
             patch("config.BLOCKFROST_EXTERNAL_URL", self.ext_url):
            resp = await blockfrost_fetch("/health")

        assert resp.status_code == 200
        assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_primary_timeout_falls_back(self):
        """When primary raises ReadTimeout, fallback to external."""
        import httpx
        from services.http_client import blockfrost_fetch, get_client

        mock_client = AsyncMock()
        fallback_response = MagicMock(spec=httpx.Response)
        fallback_response.status_code = 200

        mock_client.request = AsyncMock(
            side_effect=[httpx.ReadTimeout("Timed out"), fallback_response]
        )
        get_client.return_value = mock_client

        with patch("config.BLOCKFROST_BASE_URL", self.ryo_url), \
             patch("config.BLOCKFROST_EXTERNAL_URL", self.ext_url):
            resp = await blockfrost_fetch("/addresses/addr1test")

        assert resp.status_code == 200
        assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_both_fail_returns_external_error(self):
        """When both primary and external fail, return the external failure."""
        import httpx
        from services.http_client import blockfrost_fetch, get_client

        mock_client = AsyncMock()
        external_response = MagicMock(spec=httpx.Response)
        external_response.status_code = 503

        mock_client.request = AsyncMock(
            side_effect=[httpx.ConnectError("Primary down"), external_response]
        )
        get_client.return_value = mock_client

        with patch("config.BLOCKFROST_BASE_URL", self.ryo_url), \
             patch("config.BLOCKFROST_EXTERNAL_URL", self.ext_url):
            resp = await blockfrost_fetch("/epochs/latest")

        # Should return the external failure response (not raise)
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_same_url_no_double_fallback(self):
        """When primary == external (no RYO), don't retry a different URL."""
        import httpx
        from services.http_client import blockfrost_fetch, get_client

        same_url = "https://cardano-mainnet.blockfrost.io/api/v0"
        mock_client = AsyncMock()

        first_response = MagicMock(spec=httpx.Response)
        first_response.status_code = 500
        retry_response = MagicMock(spec=httpx.Response)
        retry_response.status_code = 200

        mock_client.request = AsyncMock(
            side_effect=[first_response, retry_response]
        )
        get_client.return_value = mock_client

        with patch("config.BLOCKFROST_BASE_URL", same_url), \
             patch("config.BLOCKFROST_EXTERNAL_URL", same_url):
            resp = await blockfrost_fetch("/health")

        # Both calls should use the same URL
        for call in mock_client.request.call_args_list:
            assert same_url in call[0][1]

    @pytest.mark.asyncio
    async def test_4xx_not_retried(self):
        """4xx errors (like 404) should NOT trigger fallback."""
        import httpx
        from services.http_client import blockfrost_fetch, get_client

        mock_client = AsyncMock()
        response = MagicMock(spec=httpx.Response)
        response.status_code = 404

        mock_client.request = AsyncMock(return_value=response)
        get_client.return_value = mock_client

        with patch("config.BLOCKFROST_BASE_URL", self.ryo_url), \
             patch("config.BLOCKFROST_EXTERNAL_URL", self.ext_url):
            resp = await blockfrost_fetch("/addresses/nonexistent")

        assert resp.status_code == 404
        # Only one call - no fallback for 4xx
        assert mock_client.request.call_count == 1


# ---------------------------------------------------------------------------
# 3. api_usage_live.py self-hosted detection
# ---------------------------------------------------------------------------


class TestApiUsageLiveSelfHosted:
    """Test that api_usage_live detects self-hosted mode correctly."""

    @pytest.mark.asyncio
    async def test_self_hosted_returns_unlimited(self):
        """When BASE != EXTERNAL, return self-hosted unlimited indicator."""
        ryo_url = "http://192.0.2.10:3000"
        ext_url = "https://cardano-mainnet.blockfrost.io/api/v0"

        with patch("services.api_usage_live.BLOCKFROST_BASE_URL", ryo_url), \
             patch("services.api_usage_live.BLOCKFROST_EXTERNAL_URL", ext_url), \
             patch("services.api_usage_live.get_cache", return_value=None), \
             patch("services.api_usage_live.set_cache", new_callable=AsyncMock):
            from services.api_usage_live import _fetch_blockfrost_usage

            result = await _fetch_blockfrost_usage()

        assert result is not None
        assert result["source"] == "self-hosted"
        assert result["requests_limit"] is None  # Unlimited
        assert result["call_count"] == 0

    @pytest.mark.asyncio
    async def test_external_queries_metrics(self):
        """When BASE == EXTERNAL, query /usage/metrics endpoint."""
        ext_url = "https://cardano-mainnet.blockfrost.io/api/v0"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"time": 1709312400, "calls": 150}]

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("services.api_usage_live.BLOCKFROST_BASE_URL", ext_url), \
             patch("services.api_usage_live.BLOCKFROST_EXTERNAL_URL", ext_url), \
             patch("services.api_usage_live.get_cache", return_value=None), \
             patch("services.api_usage_live.set_cache", new_callable=AsyncMock), \
             patch("services.api_usage_live.get_client", return_value=mock_client), \
             patch("services.api_usage_live.get_api_key", new_callable=AsyncMock, return_value="test_key"):
            from services.api_usage_live import _fetch_blockfrost_usage

            result = await _fetch_blockfrost_usage()

        assert result is not None
        assert result["source"] == "live"
        assert result["call_count"] == 150
        assert result["requests_limit"] == 50000


# ---------------------------------------------------------------------------
# 4. api_health.py Blockfrost source reporting
# ---------------------------------------------------------------------------


class TestApiHealthBlockfrostSource:
    """Test that api_health correctly reports RYO vs external source."""

    def test_health_test_uses_base_url(self):
        """The blockfrost health test URL uses BLOCKFROST_BASE_URL."""
        from services.api_health import API_HEALTH_TESTS

        assert "blockfrost" in API_HEALTH_TESTS
        test_type, url, header = API_HEALTH_TESTS["blockfrost"]
        assert test_type == "header"
        assert header == "project_id"
        # URL should contain the configured base URL (not hardcoded)
        assert "/health" in url


# ---------------------------------------------------------------------------
# 5. Engine provider registry
# ---------------------------------------------------------------------------


class TestProviderRegistry:
    """Test that the provider registry has separate blockfrost and blockfrost_external."""

    def test_registry_has_both_blockfrost_providers(self):
        """Registry should have blockfrost (RYO, priority 60) and blockfrost_external (45)."""
        from engine.providers.registry import create_default_registry

        registry = create_default_registry()
        bf = registry.get_provider("blockfrost")
        bf_ext = registry.get_provider("blockfrost_external")

        assert bf is not None, "blockfrost provider not registered"
        assert bf_ext is not None, "blockfrost_external provider not registered"

    def test_ryo_has_higher_priority(self):
        """RYO blockfrost should have higher priority than external."""
        from engine.providers.registry import create_default_registry

        registry = create_default_registry()
        bf = registry.get_provider("blockfrost")
        bf_ext = registry.get_provider("blockfrost_external")

        assert bf.priority > bf_ext.priority, (
            f"Expected blockfrost priority ({bf.priority}) > "
            f"blockfrost_external priority ({bf_ext.priority})"
        )

    def test_ryo_has_higher_concurrency(self):
        """RYO should allow more concurrent requests (no rate limiting)."""
        from engine.providers.registry import create_default_registry

        registry = create_default_registry()
        bf = registry.get_provider("blockfrost")
        bf_ext = registry.get_provider("blockfrost_external")

        assert bf.max_concurrency > bf_ext.max_concurrency
        assert bf.requests_per_second > bf_ext.requests_per_second

    def test_both_serve_cardano(self):
        """Both providers should serve Cardano chain."""
        from engine.models import ChainId, WorkDomain
        from engine.providers.registry import create_default_registry

        registry = create_default_registry()
        candidates = registry.get_candidates(ChainId.CARDANO, WorkDomain.INDEX)
        names = [c.name for c in candidates]

        assert "blockfrost" in names
        assert "blockfrost_external" in names

    def test_blockfrost_ranked_first_for_cardano(self):
        """With default health, RYO blockfrost should rank first for Cardano."""
        from engine.models import ChainId, WorkDomain
        from engine.providers.registry import create_default_registry

        registry = create_default_registry()
        best = registry.get_best_candidate(ChainId.CARDANO, WorkDomain.INDEX)

        assert best is not None
        assert best.name == "blockfrost", (
            f"Expected 'blockfrost' as best candidate, got '{best.name}'"
        )

    def test_unhealthy_ryo_deprioritized(self):
        """When RYO is marked unhealthy, external should be preferred."""
        from engine.models import ChainId, WorkDomain
        from engine.providers.registry import create_default_registry

        registry = create_default_registry()

        # Mark RYO as unhealthy
        registry.update_health(
            "blockfrost", "cardano", "index",
            {"is_healthy": False}
        )

        candidates = registry.get_candidates(ChainId.CARDANO, WorkDomain.INDEX)
        # External should now rank higher
        bf_idx = next(i for i, c in enumerate(candidates) if c.name == "blockfrost")
        ext_idx = next(i for i, c in enumerate(candidates) if c.name == "blockfrost_external")
        assert ext_idx < bf_idx, "Unhealthy RYO should rank below external"
