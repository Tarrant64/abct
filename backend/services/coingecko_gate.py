"""Single choke point for every CoinGecko HTTP call (httpx transport wrapper).

Why: on 2026-11-23 several independent callers (price refresh, mobile
summary sparklines, token metadata, charts, ...) each retried a rate-limited
request up to 4 times behind a 60 s cooldown -> hundreds of 429s per
restart. Every client built by services.http_client.get_client() is wrapped
by CoinGeckoGateTransport, which for requests to *.coingecko.com:

  * global backoff after a 429: honours Retry-After, otherwise 2 -> 4 -> 8
    -> 15 min (capped); while backing off NO network call is made and a
    synthetic 429 is returned immediately so callers use their fallbacks;
  * client-side pacing (<= PACE_PER_MIN calls/min, well under the 30/min
    demo limit); over-budget calls get the same synthetic 429;
  * in-flight de-duplication and a short (CACHE_TTL_S) response cache for
    identical GETs, so concurrent/repeated callers share ONE request;
  * attaches the CoinGecko key from the DB-stored API settings with the
    header and host matching its plan (demo -> x-cg-demo-api-key on
    api.coingecko.com, pro -> x-cg-pro-api-key on pro-api.coingecko.com);
  * counters, logged every 15 min (calls, 429s, blocked, fallback use).
"""
import asyncio
import logging
import time
from typing import Dict, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

import os
from datetime import datetime, timezone


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


PACE_PER_MIN = _env_int("PRICE_CG_CALLS_PER_MIN", 8)      # hard ceiling (demo limit is 30/min)
DAILY_BUDGET = _env_int("PRICE_CG_DAILY_BUDGET", 300)     # soft daily cap (~10k/month plan)
CACHE_TTL_S = 120.0        # identical GET reuse window
BACKOFF_STEPS_S = (120, 240, 480, 900)   # 2 -> 4 -> 8 -> 15 min cap
STATS_LOG_INTERVAL_S = 900

_clock = time.monotonic

_state = {
    "backoff_until": 0.0,
    "step": 0,
    "recent": [],            # monotonic timestamps of real network calls
}
_stats = {"calls": 0, "r429": 0, "blocked_backoff": 0,
          "blocked_pace": 0, "blocked_budget": 0, "cache_hits": 0, "dedup_hits": 0}
_fallback_use = 0
_daily = {"day": None, "n": 0}
# Extra counter providers (callables returning a dict, reset on read), logged with the 15-min line.
EXTRA_STATS = []
_last_log = [0.0]
_inflight: Dict[str, "asyncio.Future"] = {}
_cache: Dict[str, Tuple[float, int, dict, bytes]] = {}
_key_cache = {"at": 0.0, "key": None}


def is_coingecko_host(host: Optional[str]) -> bool:
    return bool(host) and (host == "coingecko.com" or host.endswith(".coingecko.com"))


def note_fallback_use(n: int = 1) -> None:
    """Called by the pricing service when a non-CoinGecko source filled a price."""
    global _fallback_use
    _fallback_use += n


def in_backoff() -> bool:
    return _clock() < _state["backoff_until"]


def backoff_remaining_s() -> int:
    return max(0, int(_state["backoff_until"] - _clock()))


def stats() -> dict:
    return {**_stats, "fallback_use": _fallback_use,
            "backoff_remaining_s": backoff_remaining_s(), "backoff_step": _state["step"]}


def _maybe_log_stats(force: bool = False) -> None:
    now = _clock()
    if not force and now - _last_log[0] < STATS_LOG_INTERVAL_S:
        return
    if _last_log[0] == 0.0 and not force:
        _last_log[0] = now
        return
    _last_log[0] = now
    s = stats()
    extra = {}
    for fn in EXTRA_STATS:
        try:
            extra.update(fn())
        except Exception:
            pass
    logger.info(
        "coingecko 15m stats: calls=%d 429=%d blocked_backoff=%d blocked_pace=%d blocked_budget=%d "
        "cache_hits=%d dedup_hits=%d fallback_use=%d backoff_remaining_s=%d day_calls=%d %s",
        s["calls"], s["r429"], s["blocked_backoff"], s["blocked_pace"], s["blocked_budget"],
        s["cache_hits"], s["dedup_hits"], s["fallback_use"], s["backoff_remaining_s"], _daily["n"],
        " ".join(f"{k}={v}" for k, v in extra.items()))
    for k in _stats:
        _stats[k] = 0
    globals()["_fallback_use"] = 0


async def stats_logger_loop() -> None:
    """Background task: emit the counter line every 15 minutes."""
    while True:
        await asyncio.sleep(STATS_LOG_INTERVAL_S)
        _maybe_log_stats(force=True)


def _register_429(retry_after: Optional[str]) -> None:
    step = _state["step"]
    delay = BACKOFF_STEPS_S[min(step, len(BACKOFF_STEPS_S) - 1)]
    try:
        if retry_after is not None:
            # honour the server's wait, never shorter than our own step
            delay = max(delay, min(float(retry_after), BACKOFF_STEPS_S[-1]))
    except (TypeError, ValueError):
        pass
    _state["step"] = step + 1
    _state["backoff_until"] = _clock() + delay
    _stats["r429"] += 1
    logger.warning("CoinGecko 429: backing off %ds (step %d); fallbacks in use", delay, step + 1)


def _register_ok() -> None:
    _state["step"] = 0


def _budget_ok() -> bool:
    day = datetime.now(timezone.utc).date()
    if _daily["day"] != day:
        _daily["day"], _daily["n"] = day, 0
    return _daily["n"] < DAILY_BUDGET


def _pace_ok() -> bool:
    now = _clock()
    recent = [t for t in _state["recent"] if now - t < 60.0]
    _state["recent"] = recent
    if len(recent) >= PACE_PER_MIN:
        return False
    recent.append(now)
    return True


def _synthetic_429(request: httpx.Request, remaining: int) -> httpx.Response:
    return httpx.Response(429, headers={"Retry-After": str(max(1, remaining)),
                                        "X-ABCT-Gate": "local"},
                          content=b'{"error":"coingecko gate: backing off"}',
                          request=request)


async def _api_key() -> Optional[str]:
    now = _clock()
    if now - _key_cache["at"] < 600 and _key_cache["at"] > 0:
        return _key_cache["key"]
    key = None
    try:
        from database import get_api_key
        key = await get_api_key("coingecko")
    except Exception:
        key = None
    _key_cache["at"] = now
    _key_cache["key"] = key or None
    return _key_cache["key"]


def _ttl_for(url: httpx.URL) -> float:
    """Reuse window per request type (see PRICING_CADENCE.md). Spot prices are
    governed by the pricing service's cadence; everything else is cached long
    so chart/metadata views never add hidden calls."""
    path = url.path
    q = str(url.query)
    if path.endswith(("/market_chart", "/ohlc")):
        days = httpx.QueryParams(q).get("days", "")
        return 1800.0 if days in ("1", "0.5") else 86400.0
    if path.endswith("/history"):
        return 86400.0
    if "/coins/markets" in path:
        if "sparkline=true" in q:
            return 3600.0
        if "ids=" not in q:
            return 3600.0     # top-N lists (market overview, metadata)
        return CACHE_TTL_S
    if path.endswith(("/global", "/search", "/trending")):
        return 3600.0
    if "/coins/" in path:
        return 86400.0        # coin metadata / images
    return CACHE_TTL_S


def is_pro_key(key: str) -> bool:
    return key.startswith("CG-") and len(key) >= 32


class CoinGeckoGateTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner: Optional[httpx.AsyncBaseTransport] = None, **kwargs):
        self._inner = inner or httpx.AsyncHTTPTransport(**kwargs)

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if not is_coingecko_host(host):
            return await self._inner.handle_async_request(request)

        _maybe_log_stats()
        if in_backoff():
            _stats["blocked_backoff"] += 1
            return _synthetic_429(request, backoff_remaining_s())

        # Plan-correct auth + host. /key and every other path alike.
        key = await _api_key()
        headers = request.headers.copy()
        for h in ("x-cg-demo-api-key", "x-cg-pro-api-key"):
            if h in headers:
                del headers[h]
        url = request.url
        if key:
            if is_pro_key(key):
                headers["x-cg-pro-api-key"] = key
                url = url.copy_with(host="pro-api.coingecko.com")
            else:
                headers["x-cg-demo-api-key"] = key
                url = url.copy_with(host="api.coingecko.com")
        request = httpx.Request(request.method, url, headers=headers,
                                content=request.content, extensions=request.extensions)

        cacheable = request.method == "GET"
        ck = f"{request.method} {request.url}" if cacheable else None
        if cacheable:
            hit = _cache.get(ck)
            if hit and _clock() - hit[0] < _ttl_for(request.url):
                _stats["cache_hits"] += 1
                return httpx.Response(hit[1], headers=hit[2], content=hit[3], request=request)
            fut = _inflight.get(ck)
            if fut is not None:
                _stats["dedup_hits"] += 1
                status, hdrs, body = await asyncio.shield(fut)
                return httpx.Response(status, headers=hdrs, content=body, request=request)
            fut = asyncio.get_running_loop().create_future()
            _inflight[ck] = fut
        try:
            if not _budget_ok():
                _stats["blocked_budget"] += 1
                resp = _synthetic_429(request, 600)
                result = (429, dict(resp.headers), resp.content)
            elif not _pace_ok():
                _stats["blocked_pace"] += 1
                resp = _synthetic_429(request, 30)
                body = resp.content
                result = (429, dict(resp.headers), body)
            else:
                _stats["calls"] += 1
                _daily["n"] += 1
                real = await self._inner.handle_async_request(request)
                body = await real.aread()
                await real.aclose()
                hdrs = {k: v for k, v in real.headers.items()
                        if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")}
                if real.status_code == 429:
                    _register_429(real.headers.get("retry-after"))
                elif real.status_code == 200:
                    _register_ok()
                    if cacheable:
                        if len(_cache) > 500:
                            _cache.clear()
                        _cache[ck] = (_clock(), 200, hdrs, body)
                result = (real.status_code, hdrs, body)
            if cacheable and not fut.done():
                fut.set_result(result)
            return httpx.Response(result[0], headers=result[1], content=result[2], request=request)
        except BaseException as exc:
            if cacheable and not fut.done():
                fut.set_exception(exc)
                fut.exception()  # mark retrieved
            raise
        finally:
            if cacheable:
                _inflight.pop(ck, None)
