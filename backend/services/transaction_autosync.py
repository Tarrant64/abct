"""Scheduled incremental transaction sync.

Transaction history used to be fetched only when a user pressed Refresh in the
web UI (``POST /transactions/refresh/start``). Clients that only read
``GET /transactions`` (the mobile app) therefore saw an empty list once the last
manual refresh was older than the requested window. This loop keeps
``transaction_history`` fresh for every real (non-demo) user.

Env: ``ABCT_TX_AUTOSYNC`` (default on; set 0/false/off to disable) and
``ABCT_TX_AUTOSYNC_INTERVAL_MIN`` (default 60, min 5).
"""

import asyncio
import logging
import os
from typing import Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_MIN = 60
INITIAL_DELAY_SEC = 180
SYNC_DAYS = 7


def autosync_enabled() -> bool:
    return os.getenv("ABCT_TX_AUTOSYNC", "1").strip().lower() not in ("0", "false", "off", "no")


def interval_seconds() -> int:
    try:
        minutes = int(os.getenv("ABCT_TX_AUTOSYNC_INTERVAL_MIN", str(DEFAULT_INTERVAL_MIN)))
    except ValueError:
        minutes = DEFAULT_INTERVAL_MIN
    return max(5, minutes) * 60


async def sync_all_users(
    list_users: Optional[Callable[[], Awaitable[List[Dict]]]] = None,
    fetch: Optional[Callable[..., Awaitable[Dict[str, int]]]] = None,
    days: int = SYNC_DAYS,
) -> Dict[int, int]:
    """Run one incremental sync for every non-demo user. Returns {user_id: rows_fetched}.

    A failure for one user is logged and does not stop the others.
    """
    if list_users is None:
        from database import get_all_users as list_users  # type: ignore
    if fetch is None:
        from services.transaction_history import transaction_history_service
        fetch = transaction_history_service.fetch_transactions

    results: Dict[int, int] = {}
    for user in await list_users():
        if user.get("is_demo"):
            continue
        uid = user["id"]
        try:
            counts = await fetch(uid, days)
            results[uid] = sum((counts or {}).values())
            logger.info("tx autosync: user %s fetched %s rows", uid, results[uid])
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("tx autosync: user %s failed: %s", uid, type(e).__name__)
    return results


async def periodic_transaction_sync() -> None:
    """Background loop: first run shortly after startup, then every interval."""
    if not autosync_enabled():
        logger.info("tx autosync disabled")
        return
    await asyncio.sleep(INITIAL_DELAY_SEC)
    while True:
        try:
            await sync_all_users()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("tx autosync cycle failed: %s", type(e).__name__)
        await asyncio.sleep(interval_seconds())
