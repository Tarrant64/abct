import asyncio
import pytest
from datetime import datetime

from services import pricing as P


def _svc(monkeypatch):
    svc = P.PricingService()
    calls = {"cg": 0}

    async def fake_cg(symbols):
        calls["cg"] += 1
        for s in symbols:
            svc.cache[s.upper()] = {"usd": 1.0, "source": "CoinGecko",
                                    "updated_at": datetime.now().isoformat()}

    async def noop(*a, **k):
        return None
    monkeypatch.setattr(svc, "_fetch_from_coingecko", fake_cg)
    for n in ("_fetch_cardano_prices", "_fetch_from_cmc", "_fetch_from_coinbase",
              "_fetch_from_coinpaprika", "_fetch_from_defillama", "_record_snapshot"):
        monkeypatch.setattr(svc, n, noop)
    monkeypatch.setattr(P, "CMC_API_KEY", None, raising=False)
    return svc, calls


@pytest.mark.asyncio
async def test_concurrent_on_demand_coalesces_and_fresh_serves_cache(monkeypatch):
    svc, calls = _svc(monkeypatch)
    await asyncio.gather(*[svc.get_prices(["BTC", "ETH"]) for _ in range(10)])
    assert calls["cg"] == 1
    await svc.get_prices(["BTC"], force_refresh=True)      # pull-to-refresh spam
    await svc.get_prices(["BTC"], force_refresh=True)
    assert calls["cg"] == 1
    assert svc.snapshot_info()["prices_as_of"]


@pytest.mark.asyncio
async def test_stale_snapshot_allows_one_refresh_then_declines(monkeypatch):
    svc, calls = _svc(monkeypatch)
    await svc.get_prices(["BTC"])
    # age the snapshot and the last attempt past the 5-minute rule
    svc.cache["BTC"]["updated_at"] = "2000-01-01T00:00:00"
    svc._last_attempt_at -= 301
    await svc.get_prices(["BTC"], force_refresh=True)
    assert calls["cg"] == 2
    svc.cache["BTC"]["updated_at"] = "2000-01-01T00:00:00"
    await svc.get_prices(["BTC"], force_refresh=True)       # attempt <5 min ago
    assert calls["cg"] == 2
    assert svc._cadence_stats["ondemand_declined"] >= 1


@pytest.mark.asyncio
async def test_hourly_cap(monkeypatch):
    svc, calls = _svc(monkeypatch)
    monkeypatch.setattr(P, "PRICE_ON_DEMAND_MAX_PER_HOUR", 2)
    for _ in range(4):
        svc.cache.get("BTC", {})["updated_at"] = "2000-01-01T00:00:00"
        svc._last_attempt_at = (svc._last_attempt_at or 0) - 301 if svc._last_attempt_at else None
        await svc.get_prices(["BTC"])
    assert calls["cg"] == 2
