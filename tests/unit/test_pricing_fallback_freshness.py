"""ABCT-V2 stale prices (2026-11-23): the fallback price sources must refresh an
expired cached price when CoinGecko is rate limited (429), instead of skipping it
because the old value is still > 0."""

import asyncio
import os
import sys
from datetime import datetime, timedelta

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from services.pricing import PricingService  # noqa: E402


def _entry(price, age):
    return {"usd": price, "updated_at": (datetime.now() - age).isoformat()}


def test_needs_price_rules():
    svc = PricingService()
    assert svc._needs_price("ADA")                                   # nothing cached
    svc.cache["ADA"] = _entry(0.144, timedelta(seconds=30))
    assert not svc._needs_price("ADA")                               # fresh
    svc.cache["ADA"] = _entry(0.144, timedelta(hours=13))
    assert svc._needs_price("ADA")                                   # expired
    svc.cache["ADA"] = {"usd": 0.144}                                # no timestamp
    assert svc._needs_price("ADA")
    svc.cache["ADA"] = _entry(0, timedelta(seconds=1))
    assert svc._needs_price("ADA")                                   # zero price


def test_defillama_refreshes_expired_price_when_coingecko_down(monkeypatch):
    svc = PricingService()
    svc.cache["ADA"] = _entry(0.14436, timedelta(hours=13))

    class Resp:
        status_code = 200
        def json(self):
            return {"coins": {"coingecko:cardano": {"price": 0.1451, "confidence": 0.99}}}

    class Client:
        async def get(self, url, **kw):
            return Resp()

    import services.pricing as pricing
    monkeypatch.setattr(pricing, "get_client", lambda *a, **k: Client())
    asyncio.run(svc._fetch_from_defillama(["ADA"], include_major=True))
    assert svc.cache["ADA"]["usd"] == 0.1451
    assert svc.cache["ADA"]["source"] == "DefiLlama"
    assert not svc._needs_price("ADA")


def test_fresh_price_is_not_refetched(monkeypatch):
    svc = PricingService()
    svc.cache["ADA"] = _entry(0.14436, timedelta(seconds=10))
    import services.pricing as pricing
    monkeypatch.setattr(pricing, "get_client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("fetched")))
    asyncio.run(svc._fetch_from_defillama(["ADA"], include_major=True))
    assert svc.cache["ADA"]["usd"] == 0.14436
