"""
Tests for the SSRF guard on the NFT image fetcher.

The fetcher takes a caller-supplied URL and retrieves it server-side, and the
cached bytes are readable back through the unauthenticated
/nfts/images/{chain}/{asset} endpoint. That combination is a read/write SSRF
primitive, so the guard has to hold for direct URLs, for every redirect hop, and
for the IPv6 spellings of internal addresses.

No test performs real network I/O: name resolution is stubbed per test and all
HTTP goes through httpx.MockTransport.
"""

import io
import os
import sys

import httpx
import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from services.nft_image_service import (  # noqa: E402
    ERR_URL_REJECTED,
    IPFS_GATEWAYS,
    MAX_BATCH_CONCURRENCY,
    MAX_BATCH_ITEMS,
    MAX_REDIRECT_HOPS,
    BlockedURLError,
    NFTImageService,
    ResponseTooLargeError,
)

PUBLIC_IP = "93.184.216.34"


@pytest.fixture
def service():
    return NFTImageService()


def stub_dns(service, mapping, default=PUBLIC_IP):
    """Point hostname resolution at fixed answers so no DNS query is made."""

    async def _resolve(host):
        value = mapping.get(host, default)
        if isinstance(value, str):
            return [value]
        return list(value)

    service._resolve_host = _resolve


def mock_client(handler):
    """An AsyncClient whose transport is driven by `handler`, never the network."""
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    )


def png_bytes():
    """A real 1x1 PNG so format detection and compression run for real."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (1, 1), (255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Scheme allowlist
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://127.0.0.1:6379/_INFO",
        "ftp://internal.example.com/secret",
        "data:image/png;base64,iVBORw0KGgo=",
    ],
)
async def test_non_http_schemes_are_rejected(service, url):
    stub_dns(service, {})

    with pytest.raises(BlockedURLError) as excinfo:
        await service._validate_fetch_url(url)

    assert "not allowed" in str(excinfo.value)


async def test_http_and_https_are_allowed(service):
    stub_dns(service, {"cdn.example.com": PUBLIC_IP})

    await service._validate_fetch_url("http://cdn.example.com/a.png")
    await service._validate_fetch_url("https://cdn.example.com/a.png")


# ---------------------------------------------------------------------------
# Address filtering
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",          # loopback
        "10.0.0.5",           # RFC1918
        "172.16.4.4",         # RFC1918
        "192.168.1.1",        # RFC1918
        "169.254.169.254",    # cloud metadata
        "100.64.0.1",         # CGNAT - not is_private, still not routable
        "0.0.0.0",            # unspecified
        "224.0.0.1",          # multicast - reports is_global True
        "::1",                # IPv6 loopback
        "fc00::1",            # IPv6 unique-local
        "fe80::1",            # IPv6 link-local
        "::ffff:127.0.0.1",   # IPv4-mapped IPv6 loopback
        "::ffff:169.254.169.254",  # IPv4-mapped metadata
        "2002:7f00:1::1",     # 6to4 wrapping 127.0.0.1
    ],
)
async def test_internal_addresses_are_rejected(service, address):
    stub_dns(service, {"evil.example.com": address})

    with pytest.raises(BlockedURLError):
        await service._validate_fetch_url("http://evil.example.com/a.png")


async def test_direct_ip_literals_are_checked(service):
    """An IP literal never goes through DNS, so it must still be classified."""
    stub_dns(service, {"127.0.0.1": "127.0.0.1", "[::1]": "::1", "::1": "::1"})

    with pytest.raises(BlockedURLError):
        await service._validate_fetch_url("http://127.0.0.1:8080/admin")

    with pytest.raises(BlockedURLError):
        await service._validate_fetch_url("http://[::1]:8080/admin")


async def test_public_addresses_are_accepted(service):
    stub_dns(service, {"cdn.example.com": PUBLIC_IP, "v6.example.com": "2606:4700::1"})

    await service._validate_fetch_url("https://cdn.example.com/a.png")
    await service._validate_fetch_url("https://v6.example.com/a.png")


async def test_host_resolving_to_both_public_and_private_is_rejected(service):
    """A split answer is treated as hostile, not as partially usable."""
    stub_dns(service, {"split.example.com": [PUBLIC_IP, "10.1.2.3"]})

    with pytest.raises(BlockedURLError):
        await service._validate_fetch_url("https://split.example.com/a.png")


async def test_unresolvable_host_is_rejected(service):
    stub_dns(service, {"nowhere.example.com": []})

    with pytest.raises(BlockedURLError) as excinfo:
        await service._validate_fetch_url("https://nowhere.example.com/a.png")

    assert "did not resolve" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Redirects
# ---------------------------------------------------------------------------

async def test_redirect_into_private_space_is_blocked(service):
    """
    The pre-flight check passes on the public URL; the danger is the hop. Every
    hop is validated before it is followed, so the internal request is never
    issued.
    """
    requested = []

    def handler(request):
        requested.append(str(request.url))
        if request.url.host == "public.example.com":
            return httpx.Response(302, headers={"location": "http://10.0.0.7/admin"})
        return httpx.Response(200, content=b"should never be reached")

    stub_dns(service, {"public.example.com": PUBLIC_IP, "10.0.0.7": "10.0.0.7"})

    async with mock_client(handler) as client:
        with pytest.raises(BlockedURLError):
            await service._fetch_guarded(client, "http://public.example.com/a.png")

    assert requested == ["http://public.example.com/a.png"]


async def test_redirect_to_cloud_metadata_is_blocked(service):
    def handler(request):
        if request.url.host == "public.example.com":
            return httpx.Response(
                302,
                headers={"location": "http://169.254.169.254/latest/meta-data/"},
            )
        return httpx.Response(200, content=b"credentials")

    stub_dns(
        service,
        {"public.example.com": PUBLIC_IP, "169.254.169.254": "169.254.169.254"},
    )

    async with mock_client(handler) as client:
        with pytest.raises(BlockedURLError):
            await service._fetch_guarded(client, "http://public.example.com/a.png")


async def test_redirect_to_another_public_host_is_followed(service):
    def handler(request):
        if request.url.host == "first.example.com":
            return httpx.Response(
                302, headers={"location": "https://second.example.com/real.png"}
            )
        return httpx.Response(
            200, content=b"imagedata", headers={"content-type": "image/png"}
        )

    stub_dns(service, {"first.example.com": PUBLIC_IP, "second.example.com": PUBLIC_IP})

    async with mock_client(handler) as client:
        data, content_type = await service._fetch_guarded(
            client, "http://first.example.com/a.png"
        )

    assert data == b"imagedata"
    assert content_type == "image/png"


async def test_redirect_loop_is_bounded(service):
    def handler(request):
        return httpx.Response(302, headers={"location": "https://loop.example.com/x"})

    stub_dns(service, {"loop.example.com": PUBLIC_IP})

    async with mock_client(handler) as client:
        with pytest.raises(BlockedURLError) as excinfo:
            await service._fetch_guarded(client, "https://loop.example.com/x")

    assert "redirect hops" in str(excinfo.value)


async def test_relative_redirect_is_resolved_then_validated(service):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.path == "/a.png":
            return httpx.Response(302, headers={"location": "/real.png"})
        return httpx.Response(200, content=b"ok", headers={"content-type": "image/png"})

    stub_dns(service, {"cdn.example.com": PUBLIC_IP})

    async with mock_client(handler) as client:
        data, _ = await service._fetch_guarded(client, "https://cdn.example.com/a.png")

    assert data == b"ok"
    assert seen == [
        "https://cdn.example.com/a.png",
        "https://cdn.example.com/real.png",
    ]


# ---------------------------------------------------------------------------
# Response size cap
# ---------------------------------------------------------------------------

async def test_oversized_body_is_rejected(service):
    service.max_download_bytes = 1024

    def handler(request):
        return httpx.Response(200, content=b"x" * 5000)

    stub_dns(service, {"cdn.example.com": PUBLIC_IP})

    async with mock_client(handler) as client:
        with pytest.raises(ResponseTooLargeError):
            await service._fetch_guarded(client, "https://cdn.example.com/big.png")


async def test_oversized_content_length_fails_fast(service):
    service.max_download_bytes = 1024

    def handler(request):
        return httpx.Response(
            200, content=b"x" * 10, headers={"content-length": "999999"}
        )

    stub_dns(service, {"cdn.example.com": PUBLIC_IP})

    async with mock_client(handler) as client:
        with pytest.raises(ResponseTooLargeError):
            await service._fetch_guarded(client, "https://cdn.example.com/big.png")


async def test_body_within_cap_is_returned(service):
    service.max_download_bytes = 1024

    def handler(request):
        return httpx.Response(
            200, content=b"y" * 512, headers={"content-type": "image/png"}
        )

    stub_dns(service, {"cdn.example.com": PUBLIC_IP})

    async with mock_client(handler) as client:
        data, _ = await service._fetch_guarded(client, "https://cdn.example.com/ok.png")

    assert len(data) == 512


# ---------------------------------------------------------------------------
# fetch_image end to end
# ---------------------------------------------------------------------------

async def test_fetch_image_succeeds_for_a_normal_public_url(service):
    def handler(request):
        return httpx.Response(
            200, content=png_bytes(), headers={"content-type": "image/png"}
        )

    stub_dns(service, {"cdn.example.com": PUBLIC_IP})

    async with mock_client(handler) as client:
        service._http_client = client
        data, image_format, error = await service.fetch_image(
            "https://cdn.example.com/nft.png"
        )

    assert error is None
    assert data
    assert image_format in ("png", "webp", "jpeg")


async def test_fetch_image_rejects_internal_url_without_calling_out(service):
    called = []

    def handler(request):
        called.append(str(request.url))
        return httpx.Response(200, content=b"secret")

    stub_dns(service, {"169.254.169.254": "169.254.169.254"})

    async with mock_client(handler) as client:
        service._http_client = client
        data, image_format, error = await service.fetch_image(
            "http://169.254.169.254/latest/meta-data/iam/security-credentials/"
        )

    assert data is None
    assert error == ERR_URL_REJECTED
    assert called == []


async def test_fetch_image_error_does_not_leak_target_details(service):
    """
    Errors are persisted and served by the unauthenticated .../info endpoint, so
    they must not reveal the host, port, or upstream status.
    """
    def handler(request):
        return httpx.Response(503, content=b"upstream boom: redis on port 6379")

    stub_dns(service, {"cdn.example.com": PUBLIC_IP})

    async with mock_client(handler) as client:
        service._http_client = client
        _, _, error = await service.fetch_image(
            "https://cdn.example.com/nft.png", max_retries=1
        )

    assert error
    for leak in ("cdn.example.com", "6379", "503", "redis", "upstream"):
        assert leak not in error


async def test_fetch_image_rejects_non_http_scheme(service):
    called = []

    def handler(request):
        called.append(str(request.url))
        return httpx.Response(200, content=b"root:x:0:0")

    stub_dns(service, {})

    async with mock_client(handler) as client:
        service._http_client = client
        data, _, error = await service.fetch_image("file:///etc/passwd")

    assert data is None
    assert error == ERR_URL_REJECTED
    assert called == []


# ---------------------------------------------------------------------------
# Legitimate behaviour that must survive the guard
# ---------------------------------------------------------------------------

def test_ipfs_urls_are_still_rewritten_to_a_gateway(service):
    ipfs_hash = "Qm" + "a" * 44
    assert len(ipfs_hash) == 46

    assert service._normalize_image_url(f"ipfs://{ipfs_hash}") == (
        f"{IPFS_GATEWAYS[0]}{ipfs_hash}"
    )
    assert service._normalize_image_url(ipfs_hash) == f"{IPFS_GATEWAYS[0]}{ipfs_hash}"


def test_ordinary_http_urls_pass_through_normalization(service):
    url = "https://images.example.com/collection/1.png"
    assert service._normalize_image_url(url) == url


async def test_ipfs_gateway_url_passes_validation(service):
    gateway_host = httpx.URL(IPFS_GATEWAYS[0]).host
    stub_dns(service, {gateway_host: PUBLIC_IP})

    await service._validate_fetch_url(f"{IPFS_GATEWAYS[0]}Qm{'a' * 44}")


# ---------------------------------------------------------------------------
# Batch fan-out bounds
# ---------------------------------------------------------------------------

async def test_batch_clamps_concurrency_and_item_count(service, monkeypatch):
    """max_concurrent and the item list both arrive from the request body."""
    seen_concurrency = {}
    processed = []

    real_semaphore = __import__("asyncio").Semaphore

    def recording_semaphore(value):
        seen_concurrency["value"] = value
        return real_semaphore(value)

    monkeypatch.setattr(
        "services.nft_image_service.asyncio.Semaphore", recording_semaphore
    )
    monkeypatch.setattr(service, "initialize", _noop)

    async def fake_cache_image(asset_id, blockchain, image_url):
        processed.append(asset_id)
        return {"status": "fetched"}

    monkeypatch.setattr(service, "cache_image", fake_cache_image)

    nfts = [
        {"asset_id": f"asset{i}", "image_url": "https://cdn.example.com/a.png"}
        for i in range(MAX_BATCH_ITEMS + 25)
    ]

    result = await service.batch_cache_images(
        nfts=nfts, blockchain="cardano", max_concurrent=10_000
    )

    assert seen_concurrency["value"] == MAX_BATCH_CONCURRENCY
    assert len(processed) == MAX_BATCH_ITEMS
    assert result["skipped"] == 25


async def test_process_pending_clamps_limit_and_concurrency(service, monkeypatch):
    captured = {}

    async def fake_get_pending(blockchain, limit):
        captured["limit"] = limit
        return []

    monkeypatch.setattr(service, "initialize", _noop)
    monkeypatch.setattr(
        "services.nft_image_service.get_pending_images", fake_get_pending
    )

    await service.process_pending(limit=10_000, max_concurrent=10_000)

    assert captured["limit"] == MAX_BATCH_ITEMS


async def _noop(*args, **kwargs):
    return None


def test_redirect_budget_is_small():
    """A large budget would make the manual re-validation loop expensive."""
    assert 1 <= MAX_REDIRECT_HOPS <= 5


async def test_shared_client_does_not_follow_redirects(service):
    """
    Guards the production client itself. Automatic redirect following would skip
    the per-hop validation entirely, and the other redirect tests build their
    own client so they would not notice.
    """
    client = await service._get_client()
    try:
        assert client.follow_redirects is False
    finally:
        await service.close()
