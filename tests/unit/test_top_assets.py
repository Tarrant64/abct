"""
Unit tests for /prices/top-assets (WATCH-5-SERVER): top coins by market cap
for the mobile watch complication gallery.

Contract: {success, assets: [{symbol, name, price, change_24h}]}, cap-ordered,
limit clamped to 1..50, cache key INCLUDES limit (the /top-movers key omits
it, which poisons differing-limit callers — this endpoint must not repeat
that), CoinPaprika fallback when CoinGecko fails. Upstream clients and the
cache layer are faked — no DB, no network, no server.
"""

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Add backend to sys.path so imports work
BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402
import routers.prices as prices  # noqa: E402
from auth_utils import verify_session  # noqa: E402

URL = "/prices/top-assets"


def _gecko_coin(rank):
    return {
        "symbol": f"tk{rank}",
        "name": f"Token {rank}",
        "current_price": 1000.0 - rank,
        "market_cap": 10_000_000_000 - rank,
        "price_change_percentage_24h": 1.234 + rank,
    }


def _paprika_ticker(rank, mcap):
    return {
        "symbol": f"PP{rank}",
        "name": f"Paprika {rank}",
        "quotes": {"USD": {
            "price": 10.0 + rank,
            "market_cap": mcap,
            "percent_change_24h": -0.456,
        }},
    }


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    """Records get() calls; serves a canned response or raises."""

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    async def get(self, url, params=None):
        self.calls.append({"url": url, "params": params or {}})
        if self.error is not None:
            raise self.error
        return self.response


@pytest.fixture
def harness(monkeypatch):
    """TestClient + call recorders for upstream clients and the cache."""
    state = {
        "gecko": _FakeClient(_FakeResponse(200, [_gecko_coin(i) for i in range(50)])),
        "paprika": _FakeClient(_FakeResponse(200, [])),
        "cache_gets": [],
        "cache_sets": [],
        "cached_value": None,
    }

    def fake_get_client(name, timeout=None):
        return state["gecko"] if name == "coingecko" else state["paprika"]

    async def fake_get_cache(key):
        state["cache_gets"].append(key)
        return state["cached_value"]

    async def fake_set_cache(key, value, ttl):
        state["cache_sets"].append({"key": key, "value": value, "ttl": ttl})

    monkeypatch.setattr(prices, "get_client", fake_get_client)
    monkeypatch.setattr(database, "get_cache", fake_get_cache)
    monkeypatch.setattr(database, "set_cache", fake_set_cache)

    app = FastAPI()
    app.include_router(prices.router)
    app.dependency_overrides[verify_session] = lambda: 1
    state["client"] = TestClient(app)
    return state


def test_response_contract_and_default_limit(harness):
    body = harness["client"].get(URL).json()

    assert body["success"] is True
    assert body["source"] == "CoinGecko"
    assert len(body["assets"]) == 20
    for asset in body["assets"]:
        assert set(asset.keys()) == {"symbol", "name", "price", "change_24h"}
    # Cap order (upstream order) preserved; symbols upper-cased.
    assert body["assets"][0]["symbol"] == "TK0"
    assert body["assets"][0]["price"] == 1000.0
    assert body["assets"][0]["change_24h"] == 1.23
    # CoinGecko asked for exactly the clamped limit, cap-ordered.
    call = harness["gecko"].calls[0]["params"]
    assert call["order"] == "market_cap_desc"
    assert call["per_page"] == 20


def test_cache_key_includes_limit(harness):
    harness["client"].get(URL + "?limit=20")
    harness["client"].get(URL + "?limit=5")

    assert harness["cache_gets"] == [
        "prices:top_assets:20",
        "prices:top_assets:5",
    ]
    assert [s["key"] for s in harness["cache_sets"]] == [
        "prices:top_assets:20",
        "prices:top_assets:5",
    ]
    # And the differing-limit responses genuinely differ.
    assert len(harness["cache_sets"][0]["value"]) == 20
    assert len(harness["cache_sets"][1]["value"]) == 5


def test_limit_clamped_to_sane_bounds(harness):
    harness["client"].get(URL + "?limit=500")
    harness["client"].get(URL + "?limit=0")

    assert harness["cache_gets"] == [
        "prices:top_assets:50",
        "prices:top_assets:1",
    ]
    assert harness["gecko"].calls[0]["params"]["per_page"] == 50
    assert harness["gecko"].calls[1]["params"]["per_page"] == 1


def test_cache_hit_short_circuits_upstream(harness):
    harness["cached_value"] = [
        {"symbol": "BTC", "name": "Bitcoin", "price": 1.0, "change_24h": 0.0}
    ]

    body = harness["client"].get(URL).json()

    assert body["source"] == "cache"
    assert body["assets"][0]["symbol"] == "BTC"
    assert harness["gecko"].calls == []
    assert harness["cache_sets"] == []


def test_coinpaprika_fallback_sorts_by_market_cap(harness):
    harness["gecko"].error = RuntimeError("CoinGecko down")
    # Deliberately unsorted market caps; fallback must rank them.
    harness["paprika"].response = _FakeResponse(200, [
        _paprika_ticker(1, mcap=50),
        _paprika_ticker(2, mcap=5000),
        _paprika_ticker(3, mcap=500),
    ])

    body = harness["client"].get(URL + "?limit=2").json()

    assert body["success"] is True
    assert body["source"] == "CoinPaprika"
    assert [a["symbol"] for a in body["assets"]] == ["PP2", "PP3"]
    assert body["assets"][0]["change_24h"] == -0.46


def test_all_sources_failing_returns_failure_not_500(harness):
    harness["gecko"].error = RuntimeError("CoinGecko down")
    harness["paprika"].error = RuntimeError("CoinPaprika down")

    response = harness["client"].get(URL)
    body = response.json()

    assert response.status_code == 200
    assert body["success"] is False
    assert body["assets"] == []
    assert harness["cache_sets"] == []
