import asyncio
import httpx
import pytest

from services import coingecko_gate as g


class _Inner(httpx.AsyncBaseTransport):
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.calls = 0
        self.seen = []

    async def handle_async_request(self, request):
        self.calls += 1
        self.seen.append(request)
        st = self.statuses.pop(0) if self.statuses else 200
        h = {"Retry-After": "1"} if st == 429 else {}
        return httpx.Response(st, headers=h, content=b'[]', request=request)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    g._state.update(backoff_until=0.0, step=0, recent=[])
    for k in g._stats:
        g._stats[k] = 0
    g._cache.clear()
    g._inflight.clear()
    g._key_cache.update(at=0.0, key=None)
    t = [1000.0]
    monkeypatch.setattr(g, "_clock", lambda: t[0])
    async def _nokey(): return None
    monkeypatch.setattr(g, "_api_key", _nokey)
    return t


def _client(inner):
    return httpx.AsyncClient(transport=g.CoinGeckoGateTransport(inner))


@pytest.mark.asyncio
async def test_429_backs_off_without_retries_and_exponentially(_reset):
    inner = _Inner([429])
    async with _client(inner) as c:
        r = await c.get("https://api.coingecko.com/api/v3/coins/markets?ids=a")
        assert r.status_code == 429 and inner.calls == 1
        r = await c.get("https://api.coingecko.com/api/v3/coins/markets?ids=b")
        assert r.status_code == 429 and inner.calls == 1  # blocked locally
        assert g.backoff_remaining_s() == 120
        _reset[0] += 121
        inner.statuses = [429]
        await c.get("https://api.coingecko.com/api/v3/coins/markets?ids=c")
        assert g.backoff_remaining_s() == 240  # 2 -> 4 min


@pytest.mark.asyncio
async def test_dedup_and_cache(_reset):
    inner = _Inner([])
    async with _client(inner) as c:
        url = "https://api.coingecko.com/api/v3/coins/markets?ids=a"
        await asyncio.gather(*[c.get(url) for _ in range(5)])
        await c.get(url)
        assert inner.calls == 1


@pytest.mark.asyncio
async def test_pacing_and_non_coingecko_passthrough(_reset):
    inner = _Inner([])
    async with _client(inner) as c:
        for i in range(g.PACE_PER_MIN + 5):
            await c.get(f"https://api.coingecko.com/api/v3/coins/x{i}/ohlc")
        assert inner.calls == g.PACE_PER_MIN
        for i in range(3):
            await c.get(f"https://example.com/{i}")
        assert inner.calls == g.PACE_PER_MIN + 3


@pytest.mark.asyncio
async def test_key_header_by_plan(monkeypatch):
    inner = _Inner([])
    async def demo(): return "CG-shortdemo"
    monkeypatch.setattr(g, "_api_key", demo)
    async with _client(inner) as c:
        await c.get("https://api.coingecko.com/api/v3/ping")
    assert inner.seen[0].headers["x-cg-demo-api-key"] == "CG-shortdemo"
    assert "x-cg-pro-api-key" not in inner.seen[0].headers
    inner2 = _Inner([])
    pro = "CG-" + "x" * 40
    async def prok(): return pro
    monkeypatch.setattr(g, "_api_key", prok)
    g._cache.clear()
    async with _client(inner2) as c:
        await c.get("https://api.coingecko.com/api/v3/ping")
    assert inner2.seen[0].headers["x-cg-pro-api-key"] == pro
    assert inner2.seen[0].url.host == "pro-api.coingecko.com"
