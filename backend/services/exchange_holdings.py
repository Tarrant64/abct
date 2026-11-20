"""Exchange holdings loader for the holdings/breakdown endpoints.

The `<name>_portfolio` cache rows expire after 5 minutes, and the callers
(all-holdings, wallet-breakdown, mobile summary top-holdings) used to read
them cache-only -- so every expiry silently dropped that exchange's balances
from the response. This loader never omits an exchange it knows about:

  fresh        a live cache row
  stale        the expired row is served (marked stale) and a single-flight
               background refresh is started
  live         no row at all: fetched in-request, bounded by a timeout
  warming      no row, fetch still running past the timeout (it keeps running
               and fills the cache); the response is marked incomplete
  unavailable  no row and the fetch failed
  not_configured  the exchange has no credentials (genuinely not a holding)

Every exchange in get_aggregation_exchange_names() (legacy 7 + registry) is
considered.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Tuple

from database import get_cache, get_stale_cache
from services.exchange_names import (
    get_aggregation_exchange_names,
    get_exchange_display_name,
)

logger = logging.getLogger(__name__)

# In-request wait for a cold (no row at all) exchange. The fetch is shielded:
# on timeout it keeps running in the background and fills the cache.
COLD_FETCH_TIMEOUT_S = 6.0
# After an attempt (success with nothing cacheable, failure, 503) the same
# exchange is not retried for this long, so a broken exchange can't turn
# every request into an upstream call.
RETRY_BACKOFF_S = 45.0

_inflight: Dict[Tuple[int, str], "asyncio.Task"] = {}
_last_attempt: Dict[Tuple[int, str], Tuple[float, str, Optional[dict]]] = {}


async def _fetch_live(user_id: int, name: str) -> dict:
    from routers.exchanges import fetch_exchange_portfolio
    return await fetch_exchange_portfolio(name, user_id, False)


def _start_fetch(user_id: int, name: str) -> "asyncio.Task":
    key = (user_id, name)
    task = _inflight.get(key)
    if task is not None and not task.done():
        return task

    async def _run():
        try:
            data = await _fetch_live(user_id, name)
            _last_attempt[key] = (time.monotonic(), "ok", data)
            return data
        except Exception as e:
            status_code = getattr(e, "status_code", None)
            _last_attempt[key] = (
                time.monotonic(),
                "not_configured" if status_code in (404, 503) else "error",
                None,
            )
            if status_code not in (404, 503):
                logger.warning("exchange %s live fetch failed: %s", name, e)
            raise
        finally:
            _inflight.pop(key, None)

    task = asyncio.ensure_future(_run())
    _inflight[key] = task
    # never leave an unretrieved exception on a fire-and-forget task
    task.add_done_callback(lambda t: t.cancelled() or t.exception())
    return task


def _recent_attempt(user_id: int, name: str):
    row = _last_attempt.get((user_id, name))
    if row and time.monotonic() - row[0] < RETRY_BACKOFF_S:
        return row
    return None


async def _load_one(user_id: int, name: str, allow_live: bool, timeout: float) -> dict:
    out = {
        "exchange_id": name,
        "display_name": get_exchange_display_name(name),
        "data": None,
        "status": "unavailable",
        "stale": False,
    }
    fresh = await get_cache(f"{name}_portfolio", user_id=user_id)
    if fresh:
        out.update(data=fresh, status="fresh")
        return out

    stale, _ = await get_stale_cache(f"{name}_portfolio", user_id=user_id)
    if stale:
        out.update(data=stale, status="stale", stale=True)
        if allow_live and not _recent_attempt(user_id, name):
            _start_fetch(user_id, name)
        return out

    if not allow_live:
        out["status"] = "unavailable"
        return out

    recent = _recent_attempt(user_id, name)
    if recent:
        _, state, data = recent
        if state == "ok" and data is not None:
            out.update(data=data, status="live")
        elif state == "not_configured":
            out["status"] = "not_configured"
        return out

    task = _start_fetch(user_id, name)
    done, _pending = await asyncio.wait({task}, timeout=timeout)
    if not done:
        out["status"] = "warming"
        return out
    try:
        out.update(data=task.result(), status="live")
    except Exception as e:
        out["status"] = "not_configured" if getattr(e, "status_code", None) in (404, 503) else "unavailable"
    return out


async def load_exchange_portfolios(
    user_id: int,
    names: Optional[List[str]] = None,
    allow_live: bool = True,
    timeout: float = COLD_FETCH_TIMEOUT_S,
) -> List[dict]:
    """Load every aggregation exchange; see module docstring for statuses."""
    names = list(names) if names is not None else get_aggregation_exchange_names()
    return list(await asyncio.gather(
        *[_load_one(user_id, n, allow_live, timeout) for n in names]
    ))


def incomplete(loads: List[dict]) -> List[dict]:
    """Loads whose data is missing for a reason other than 'not configured'."""
    return [l for l in loads if l["data"] is None and l["status"] in ("warming", "unavailable")]
