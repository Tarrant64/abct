"""
Portfolio freshness: write-path cache invalidation + cheap change token.

Problem this solves (ABCT-ASSET-FRESHNESS-20261117): editing a manual stock /
custom token / wallet changed the source row, but the server-side derived
caches (portfolio summary, totals, all-holdings, charts, mobile summary...)
and the `portfolio_positions` snapshot kept serving the old quantity until a
full SYNC. Every state-changing endpoint that alters what the portfolio
holds must call `invalidate_user_portfolio_caches` (or use the
`@invalidates_portfolio` decorator, which does it after a successful return).

Also exposes a per-user "portfolio version" token. It changes on every
invalidation, so a tab that regains focus can compare one tiny value instead
of refetching everything or polling external APIs.
"""

import functools
import logging
import time
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# `clear_cache` matches with LIKE %pattern% scoped to the user's rows, so a
# prefix covers every variant (e.g. all_holdings_v2_{uid} and ..._all).
_VERSION_TTL_SECONDS = 10 * 365 * 24 * 3600


def _patterns(user_id: int) -> list:
    uid = int(user_id)
    return [
        f"portfolio_summary_{uid}",
        f"portfolio_totals_{uid}",
        f"portfolio_instant_{uid}",
        f"portfolio_analytics_{uid}",
        f"all_holdings_{uid}",        # legacy key shape
        f"all_holdings_v2_{uid}",     # superseded by v3 (kept so old rows still clear)
        f"all_holdings_v3_{uid}",     # current (covers the _all variant)
        f"unified_chart_v2_{uid}_",
        f"unified_chart_{uid}_",
        f"portfolio_24h_hourly_v2_{uid}",
        "asset_breakdown_",           # asset_breakdown_{chain}_{uid}
        "price_chart_v2_",            # price_chart_v2_{chain}_{tf}_{uid}
        f"mobile_portfolio_summary_v2_{uid}_",  # superseded by v3
        f"mobile_portfolio_summary_v3_{uid}_",
    ]


async def invalidate_user_portfolio_caches(
    user_id: int,
    reason: str = "",
    wallet_ids: Optional[Iterable[int]] = None,
    clear_stock_positions: bool = False,
) -> str:
    """Drop every derived portfolio cache for one user and bump the version.

    wallet_ids: also drop those wallets' per-wallet balance caches
        (`wallet_balance_{id}`), which the summary otherwise re-serves.
    clear_stock_positions: delete the user's `portfolio_positions` rows of
        source_type 'manual_stock' (stale snapshot of stock quantities; the
        instant endpoint re-reads manual_stocks directly).
    Never raises: invalidation is best-effort and must not fail the write.
    Returns the new version token.
    """
    from database import clear_cache, set_cache

    for pattern in _patterns(user_id):
        try:
            await clear_cache(pattern, user_id=user_id)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("portfolio invalidation: clear %s failed: %s", pattern, e)

    for wid in (wallet_ids or ()):
        try:
            await clear_cache(f"wallet_balance_{int(wid)}", user_id=user_id)
        except Exception as e:  # pragma: no cover
            logger.warning("portfolio invalidation: wallet %s cache clear failed: %s", wid, e)

    if clear_stock_positions:
        try:
            from database import clear_portfolio_positions
            await clear_portfolio_positions(user_id, "manual_stock")
        except Exception as e:  # pragma: no cover
            logger.warning("portfolio invalidation: stock positions clear failed: %s", e)

    token = str(time.time_ns())
    try:
        await set_cache(f"portfolio_version_{int(user_id)}", {"v": token},
                        _VERSION_TTL_SECONDS, user_id=user_id)
    except Exception as e:  # pragma: no cover
        logger.warning("portfolio invalidation: version bump failed: %s", e)
    logger.info("portfolio caches invalidated user=%s reason=%s", user_id, reason)
    return token


async def get_portfolio_version(user_id: int) -> str:
    """Opaque change token ('0' if never bumped / cleared). Cheap: one row."""
    from database import get_cache
    row = await get_cache(f"portfolio_version_{int(user_id)}", user_id=user_id)
    if isinstance(row, dict) and row.get("v"):
        return str(row["v"])
    return "0"


def invalidates_portfolio(reason: str, clear_stock_positions: bool = False):
    """Decorator for async endpoints taking a `user_id` kwarg.

    Runs the invalidation only after the endpoint returned without raising,
    so a rejected edit (404/400) does not churn caches. Place it BELOW the
    `@router.<verb>` line.
    """
    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            result = await fn(*args, **kwargs)
            uid = kwargs.get("user_id")
            if uid is not None:
                await invalidate_user_portfolio_caches(
                    uid, reason, clear_stock_positions=clear_stock_positions)
            return result
        return wrapper
    return deco
