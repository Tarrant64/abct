"""
Unified Cardano data access layer with triple fallback.

Priority: Direct SQL → Blockfrost RYO → Blockfrost.io

This is the core pattern for migrating Blockfrost calls to direct DB access.
When DBSYNC_PG_ENABLED is False, the SQL path is skipped entirely and
Blockfrost is used as before — zero behavior change.
"""

import logging
from typing import Any, Optional, Callable

logger = logging.getLogger(__name__)


class CardanoQueryError(Exception):
    """All data sources failed."""
    pass


async def cardano_query(
    *,
    sql_fn: Optional[Callable] = None,
    blockfrost_fn: Optional[Callable] = None,
    operation: str = "unknown",
) -> Any:
    """
    Execute a Cardano data query with triple fallback.

    Args:
        sql_fn: Async function that queries DB Sync directly via asyncpg.
                Should return the result or raise on failure.
        blockfrost_fn: Async function that queries via blockfrost_fetch().
                       Already has RYO→external fallback built in.
        operation: Human-readable operation name for logging.

    Returns:
        Result from whichever source succeeds first.

    Raises:
        CardanoQueryError if all sources fail.
    """
    from config import DBSYNC_PG_ENABLED
    errors = []

    # Source 1: Direct SQL (fastest, no rate limits)
    if DBSYNC_PG_ENABLED and sql_fn is not None:
        try:
            result = await sql_fn()
            logger.debug(f"[{operation}] served from direct SQL")
            return result
        except Exception as e:
            errors.append(f"SQL: {e}")
            logger.warning(f"[{operation}] direct SQL failed: {e}")

    # Source 2+3: Blockfrost (RYO first, then external — handled by blockfrost_fetch)
    if blockfrost_fn is not None:
        try:
            result = await blockfrost_fn()
            logger.debug(f"[{operation}] served from Blockfrost")
            return result
        except Exception as e:
            errors.append(f"Blockfrost: {e}")
            logger.warning(f"[{operation}] Blockfrost failed: {e}")

    raise CardanoQueryError(
        f"[{operation}] all sources failed: {'; '.join(errors)}"
    )
